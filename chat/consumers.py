import json
from django.utils import timezone
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from .models import Message, Group, GroupMessage

User = get_user_model()


class ChatConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for 1-on-1 real-time messaging."""

    async def connect(self):
        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            await self.close()
            return
        self.other_username = self.scope["url_route"]["kwargs"]["username"]

        # Enforce admin visibility: normal users cannot chat with admin/staff users via WS
        other_user = await self.get_other_user(self.other_username)
        if other_user is None:
            await self.close()
            return
        if (other_user.is_superuser or other_user.is_staff) and \
                not (self.user.is_superuser or self.user.is_staff):
            await self.close()
            return

        usernames = sorted([self.user.username, self.other_username])
        self.room_name = f'chat_{"_".join(usernames)}'
        await self.channel_layer.group_add(self.room_name, self.channel_name)
        await self.accept()
        count = await self.mark_messages_read()
        # Tell the room (including the other user's open tab) that we've read their messages
        # so the home-page badge can be cleared instantly without a refresh
        if count > 0:
            await self.channel_layer.group_send(
                self.room_name,
                {
                    'type': 'read_receipt',
                    'reader': self.user.username,
                }
            )
            # Also clear badge on the other user's home page via their notif channel
            await self.channel_layer.group_send(
                f'notif_{self.other_username}',
                {
                    'type': 'read_receipt_notif',
                    'reader': self.user.username,
                    'chat_partner': self.other_username,
                }
            )

    async def disconnect(self, close_code):
        if hasattr(self, "room_name"):
            await self.channel_layer.group_discard(self.room_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)

        # ── File / Voice message ──
        if data.get("file_message"):
            avatar = await self.get_avatar()
            file_type = data.get("file_type", "document")
            file_name = data.get("file_name", "")
            ts = data.get("timestamp", "")
            # Choose a human-readable preview label
            if file_type == "voice":
                preview = "🎤 Voice message"
            elif file_type == "image":
                preview = "🖼 Image"
            elif file_type == "video":
                preview = "🎬 Video"
            else:
                preview = f"📎 {file_name}" if file_name else "📎 File"

            await self.channel_layer.group_send(
                self.room_name,
                {
                    "type": "chat_message",
                    "file_message": True,
                    "file_url": data.get("file_url", ""),
                    "file_name": file_name,
                    "file_type": file_type,
                    "file_size": data.get("file_size", ""),
                    "message": data.get("caption", ""),
                    "sender": self.user.username,
                    "sender_avatar": avatar,
                    "timestamp": ts,
                    "message_id": data.get("message_id", -1),
                },
            )

            # Notify receiver's home page (so unread badge & preview update in real time)
            chat_url = f"/chat/room/{self.user.username}/"
            await self.channel_layer.group_send(
                f"notif_{self.other_username}",
                {
                    "type": "new_message",
                    "sender": self.user.username,
                    "sender_avatar": avatar,
                    "preview": preview,
                    "timestamp": ts,
                    "chat_url": chat_url,
                    "is_group": False,
                    "file_type": file_type,
                },
            )
            return

        # ── Text message ──
        message_content = data.get("message", "").strip()
        if not message_content:
            return
        message = await self.save_message(message_content)
        avatar = await self.get_avatar()
        ts = timezone.localtime(message.timestamp).strftime("%I:%M %p")
        chat_url = f"/chat/room/{self.user.username}/"

        await self.channel_layer.group_send(
            self.room_name,
            {
                "type": "chat_message",
                "message": message_content,
                "sender": self.user.username,
                "sender_avatar": avatar,
                "timestamp": ts,
                "message_id": message.id,
            },
        )

        # Notify receiver's home page in real time
        await self.channel_layer.group_send(
            f"notif_{self.other_username}",
            {
                "type": "new_message",
                "sender": self.user.username,
                "sender_avatar": avatar,
                "preview": message_content[:60],
                "timestamp": ts,
                "chat_url": chat_url,
                "is_group": False,
                "file_type": "text",
            },
        )

    async def chat_message(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "message",
                    "message": event.get("message", ""),
                    "sender": event["sender"],
                    "sender_avatar": event.get("sender_avatar", ""),
                    "timestamp": event.get("timestamp", ""),
                    "message_id": event.get("message_id", -1),
                    "file_message": event.get("file_message", False),
                    "file_url": event.get("file_url", ""),
                    "file_name": event.get("file_name", ""),
                    "file_type": event.get("file_type", ""),
                    "file_size": event.get("file_size", ""),
                }
            )
        )

    @database_sync_to_async
    def get_other_user(self, username):
        """Return the User object for the other chat participant, or None."""
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist:
            return None

    @database_sync_to_async
    def save_message(self, content):
        other_user = User.objects.get(username=self.other_username)
        msg = Message(sender=self.user, receiver=other_user)
        msg.set_message(content)  # AES-256 encrypt before saving
        msg.save()
        return msg

    @database_sync_to_async
    def mark_messages_read(self):
        try:
            other_user = User.objects.get(username=self.other_username)
            count = Message.objects.filter(
                sender=other_user, receiver=self.user, is_read=False
            ).update(is_read=True)
            return count
        except User.DoesNotExist:
            return 0

    async def read_receipt(self, event):
        """Forward read-receipt to both sides of the chat room."""
        await self.send(text_data=json.dumps({
            'type': 'read_receipt',
            'reader': event['reader'],
        }))

    @database_sync_to_async
    def get_avatar(self):
        return self.user.avatar.url if self.user.avatar else ""


class GroupChatConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for group chat rooms."""

    async def connect(self):
        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            await self.close()
            return
        self.group_id = self.scope["url_route"]["kwargs"]["group_id"]
        self.room_name = f"group_{self.group_id}"
        if not await self.check_membership():
            await self.close()
            return
        await self.channel_layer.group_add(self.room_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "room_name"):
            await self.channel_layer.group_discard(self.room_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)

        if data.get("file_message"):
            avatar = await self.get_avatar()
            file_type = data.get("file_type", "document")
            file_name = data.get("file_name", "")
            ts = data.get("timestamp", "")
            if file_type == "voice":
                preview = "🎤 Voice message"
            elif file_type == "image":
                preview = "🖼 Image"
            elif file_type == "video":
                preview = "🎬 Video"
            else:
                preview = f"📎 {file_name}" if file_name else "📎 File"

            await self.channel_layer.group_send(
                self.room_name,
                {
                    "type": "group_message",
                    "file_message": True,
                    "file_url": data.get("file_url", ""),
                    "file_name": file_name,
                    "file_type": file_type,
                    "file_size": data.get("file_size", ""),
                    "message": "",
                    "sender": self.user.username,
                    "sender_avatar": avatar,
                    "timestamp": ts,
                    "message_id": data.get("message_id", -1),
                },
            )

            # Notify all group members' home pages
            group_name = await self.get_group_name()
            member_usernames = await self.get_member_usernames()
            for uname in member_usernames:
                if uname != self.user.username:
                    await self.channel_layer.group_send(
                        f"notif_{uname}",
                        {
                            "type": "new_message",
                            "sender": self.user.username,
                            "sender_avatar": avatar,
                            "preview": preview,
                            "timestamp": ts,
                            "chat_url": f"/chat/group/{self.group_id}/",
                            "is_group": True,
                            "group_name": group_name,
                            "file_type": file_type,
                        },
                    )
            return

        message_content = data.get("message", "").strip()
        if not message_content:
            return
        msg = await self.save_group_message(message_content)
        avatar = await self.get_avatar()
        ts = timezone.localtime(msg.timestamp).strftime("%I:%M %p")
        group_name = await self.get_group_name()

        await self.channel_layer.group_send(
            self.room_name,
            {
                "type": "group_message",
                "message": message_content,
                "sender": self.user.username,
                "sender_avatar": avatar,
                "timestamp": ts,
                "message_id": msg.id,
                "file_message": False,
            },
        )

        # Notify all group members' home pages
        member_usernames = await self.get_member_usernames()
        for uname in member_usernames:
            if uname != self.user.username:
                await self.channel_layer.group_send(
                    f"notif_{uname}",
                    {
                        "type": "new_message",
                        "sender": self.user.username,
                        "sender_avatar": avatar,
                        "preview": message_content[:60],
                        "timestamp": ts,
                        "chat_url": f"/chat/group/{self.group_id}/",
                        "is_group": True,
                        "group_name": group_name,
                        "file_type": "text",
                    },
                )

    async def group_message(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "message",
                    "message": event.get("message", ""),
                    "sender": event["sender"],
                    "sender_avatar": event.get("sender_avatar", ""),
                    "timestamp": event.get("timestamp", ""),
                    "message_id": event.get("message_id", -1),
                    "file_message": event.get("file_message", False),
                    "file_url": event.get("file_url", ""),
                    "file_name": event.get("file_name", ""),
                    "file_type": event.get("file_type", ""),
                    "file_size": event.get("file_size", ""),
                }
            )
        )

    @database_sync_to_async
    def check_membership(self):
        try:
            group = Group.objects.get(id=self.group_id)
            return group.members.filter(id=self.user.id).exists()
        except Group.DoesNotExist:
            return False

    @database_sync_to_async
    def save_group_message(self, content):
        group = Group.objects.get(id=self.group_id)
        msg = GroupMessage(group=group, sender=self.user)
        msg.set_message(content)  # AES-256 encrypt before saving
        msg.save()
        return msg

    @database_sync_to_async
    def get_avatar(self):
        return self.user.avatar.url if self.user.avatar else ""

    @database_sync_to_async
    def get_group_name(self):
        try:
            return Group.objects.get(id=self.group_id).name
        except Group.DoesNotExist:
            return "Group"

    @database_sync_to_async
    def get_member_usernames(self):
        try:
            return list(
                Group.objects.get(id=self.group_id).members.values_list(
                    "username", flat=True
                )
            )
        except Group.DoesNotExist:
            return []


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    Global consumer — one per logged-in user.
    Receives new message notifications from any chat/group
    so the home page updates in real time without refresh.
    """

    async def connect(self):
        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            await self.close()
            return
        # Each user joins their own personal notification channel
        self.group_name = f"notif_{self.user.username}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        pass  # client never sends to this socket

    async def new_message(self, event):
        """Push a new-message event to this user's home page."""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "new_message",
                    "sender": event["sender"],
                    "sender_avatar": event.get("sender_avatar", ""),
                    "preview": event.get("preview", ""),
                    "timestamp": event.get("timestamp", ""),
                    "chat_url": event.get("chat_url", ""),
                    "is_group": event.get("is_group", False),
                    "group_name": event.get("group_name", ""),
                    "file_type": event.get("file_type", ""),
                }
            )
        )

    async def read_receipt_notif(self, event):
        """Tell the home page to clear the unread badge for this conversation."""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "read_receipt",
                    "reader": event["reader"],
                    "chat_partner": event.get("chat_partner", ""),
                }
            )
        )
