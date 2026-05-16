"""
Chat views — all messages saved with AES-256 encryption (AES-256-CBC).
Encryption/Decryption handled by chat.encryption module.
"""
import json
import os
import uuid
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.contrib import messages as django_messages
from django.utils import timezone
from .models import Message, Group, GroupMessage
from .encryption import encrypt_message, decrypt_message

User = get_user_model()
MAX_FILE_SIZE = 5 * 1024 * 1024 * 1024  # 5 GB


def get_file_type(name):
    ext = (name.split('.')[-1] if '.' in name else '').lower()
    if ext in ['jpg','jpeg','png','gif','webp','bmp','svg']: return 'image'
    if ext in ['mp4','webm','mov','avi','mkv','flv','wmv','m4v']: return 'video'
    if ext in ['mp3','wav','ogg','aac','flac','m4a']: return 'audio'
    if ext == 'pdf': return 'pdf'
    if ext in ['zip','rar','7z','tar','gz']: return 'archive'
    return 'document'


def format_size(b):
    if b < 1024: return f'{b} B'
    if b < 1024**2: return f'{b/1024:.1f} KB'
    if b < 1024**3: return f'{b/1048576:.1f} MB'
    return f'{b/1073741824:.2f} GB'


@login_required
def home_view(request):
    sent_to       = Message.objects.filter(sender=request.user).values_list('receiver', flat=True)
    received_from = Message.objects.filter(receiver=request.user).values_list('sender', flat=True)
    chatted_ids   = set(list(sent_to) + list(received_from))

    conversations = []
    for uid in chatted_ids:
        try:
            other = User.objects.get(pk=uid)
        except User.DoesNotExist:
            continue
        # Hide admin conversations from non-admin users; skip ghost 'None' account
        if other.is_superuser and not request.user.is_superuser:
            continue
        if other.username == 'None':
            continue
        last  = Message.objects.filter(
            Q(sender=request.user, receiver=other) |
            Q(sender=other, receiver=request.user)
        ).order_by('-timestamp').first()
        unread = Message.objects.filter(sender=other, receiver=request.user, is_read=False).count()
        conversations.append({'user': other, 'last_message': last, 'unread_count': unread})

    conversations.sort(
        key=lambda x: x['last_message'].timestamp if x['last_message'] else 0, reverse=True)
    # Exclude superusers from People sidebar for non-admin users
    if request.user.is_superuser:
        all_users = User.objects.exclude(pk=request.user.pk).exclude(pk__in=chatted_ids).exclude(username='None')
    else:
        all_users = User.objects.exclude(pk=request.user.pk).exclude(pk__in=chatted_ids).exclude(is_superuser=True).exclude(username='None')
    user_groups = request.user.group_memberships.all().order_by('-created_at')

    return render(request, 'chat/home.html', {
        'conversations': conversations,
        'all_users': all_users,
        'user_groups': user_groups,
    })


@login_required
def chat_room_view(request, username):
    other_user = get_object_or_404(User, username=username)
    if other_user == request.user:
        return redirect('chat:home')
    # Non-admin users cannot open a chat with an admin/superuser
    if other_user.is_superuser and not request.user.is_superuser:
        from django.contrib import messages as dj_msg
        dj_msg.error(request, 'This user is not available for direct messaging.')
        return redirect('chat:home')
    messages_qs = Message.objects.filter(
        Q(sender=request.user, receiver=other_user) |
        Q(sender=other_user, receiver=request.user)
    ).order_by('timestamp')
    Message.objects.filter(
        sender=other_user, receiver=request.user, is_read=False).update(is_read=True)
    return render(request, 'chat/room.html', {
        'other_user': other_user,
        'messages': messages_qs,
    })


@login_required
def search_users_view(request):
    query   = request.GET.get('q', '').strip()
    results = []
    if query:
        results = User.objects.filter(username__icontains=query).exclude(pk=request.user.pk)
        if not request.user.is_superuser:
            results = results.exclude(is_superuser=True)
    return render(request, 'chat/search.html', {'results': results, 'query': query})


# ── Group Views ────────────────────────────────────────────────────────────────

@login_required
def create_group_view(request):
    if request.user.is_superuser:
        all_users = User.objects.exclude(pk=request.user.pk)
    else:
        all_users = User.objects.exclude(pk=request.user.pk).exclude(is_superuser=True)
    if request.method == 'POST':
        name       = request.POST.get('name', '').strip()
        desc       = request.POST.get('description', '').strip()
        member_ids = request.POST.getlist('members')
        icon       = request.FILES.get('icon')
        if not name:
            django_messages.error(request, 'Group name is required.')
            return render(request, 'chat/create_group.html', {'all_users': all_users})
        group = Group.objects.create(name=name, description=desc, created_by=request.user)
        if icon:
            group.icon = icon; group.save()
        group.members.add(request.user)
        for uid in member_ids:
            try: group.members.add(User.objects.get(pk=uid))
            except User.DoesNotExist: pass
        django_messages.success(request, f'Group "{name}" created!')
        return redirect('chat:group_room', group_id=group.id)
    return render(request, 'chat/create_group.html', {'all_users': all_users})


@login_required
def group_room_view(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if not group.members.filter(id=request.user.id).exists():
        django_messages.error(request, 'You are not a member of this group.')
        return redirect('chat:home')
    msgs    = GroupMessage.objects.filter(group=group).select_related('sender').order_by('timestamp')
    members = group.members.all()
    return render(request, 'chat/group_room.html', {
        'group': group, 'messages': msgs,
        'members': members, 'is_admin': group.created_by == request.user,
    })


@login_required
@require_POST
def group_upload_file_view(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if not group.members.filter(id=request.user.id).exists():
        return JsonResponse({'error': 'Not a member'}, status=403)
    f = request.FILES.get('file')
    if not f: return JsonResponse({'error': 'No file'}, status=400)
    if f.size > MAX_FILE_SIZE: return JsonResponse({'error': 'File exceeds 5 GB'}, status=400)
    ft = get_file_type(f.name)
    msg = GroupMessage(group=group, sender=request.user, file_name=f.name, file_type=ft)
    msg.set_message('')  # no text content for file messages
    msg.file = f
    msg.save()
    return JsonResponse({
        'ok': True, 'message_id': msg.id, 'sender': request.user.username,
        'timestamp': timezone.localtime(msg.timestamp).strftime('%I:%M %p'),
        'file_url': msg.file.url, 'file_name': f.name,
        'file_type': ft, 'file_size': format_size(f.size),
    })


@login_required
@require_POST
def add_member_view(request, group_id):
    group    = get_object_or_404(Group, id=group_id, created_by=request.user)
    username = request.POST.get('username', '').strip()
    try:
        user = User.objects.get(username=username)
        group.members.add(user)
        django_messages.success(request, f'{username} added.')
    except User.DoesNotExist:
        django_messages.error(request, f'User "{username}" not found.')
    return redirect('chat:group_room', group_id=group_id)


@login_required
@require_POST
def leave_group_view(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    group.members.remove(request.user)
    django_messages.success(request, f'You left "{group.name}".')
    return redirect('chat:home')


# ── HTTP fallback send (no WS) ─────────────────────────────────────────────────

@login_required
@require_POST
@csrf_protect
def send_message_view(request):
    try:
        data     = json.loads(request.body)
        plaintext = data.get('message', '').strip()
        recv_name = data.get('receiver', '')
        if not plaintext or not recv_name:
            return JsonResponse({'error': 'Missing data'}, status=400)
        receiver = get_object_or_404(User, username=recv_name)
        msg = Message(sender=request.user, receiver=receiver)
        msg.set_message(plaintext)   # ← AES-256 encrypt
        msg.save()
        return JsonResponse({
            'ok': True, 'message': plaintext, 'sender': request.user.username,
            'timestamp': timezone.localtime(msg.timestamp).strftime('%I:%M %p'),
            'message_id': msg.id,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ── File upload ────────────────────────────────────────────────────────────────

@login_required
@require_POST
def upload_file_view(request):
    recv_name = request.POST.get('receiver', '')
    if not recv_name: return JsonResponse({'error': 'No receiver'}, status=400)
    receiver = get_object_or_404(User, username=recv_name)
    f = request.FILES.get('file')
    if not f: return JsonResponse({'error': 'No file'}, status=400)
    if f.size > MAX_FILE_SIZE: return JsonResponse({'error': 'File exceeds 5 GB'}, status=400)
    ft = get_file_type(f.name)
    msg = Message(sender=request.user, receiver=receiver, file_name=f.name, file_type=ft)
    msg.set_message('')   # no text for file-only messages
    msg.file = f
    msg.save()
    return JsonResponse({
        'ok': True, 'message_id': msg.id, 'sender': request.user.username,
        'timestamp': timezone.localtime(msg.timestamp).strftime('%I:%M %p'),
        'file_url': msg.file.url, 'file_name': f.name,
        'file_type': ft, 'file_size': format_size(f.size),
    })


# ── Voice upload ───────────────────────────────────────────────────────────────

@login_required
@require_POST
def upload_voice_view(request):
    recv_name = request.POST.get('receiver', '')
    if not recv_name: return JsonResponse({'error': 'No receiver'}, status=400)
    receiver  = get_object_or_404(User, username=recv_name)
    blob      = request.FILES.get('voice')
    if not blob: return JsonResponse({'error': 'No audio'}, status=400)
    ct = blob.content_type or 'audio/webm'
    ext = 'ogg' if 'ogg' in ct else 'webm'
    blob.name = f'voice_{uuid.uuid4().hex}.{ext}'
    msg = Message(sender=request.user, receiver=receiver, file_name=blob.name, file_type='voice')
    msg.set_message('')
    msg.file = blob
    msg.save()
    return JsonResponse({
        'ok': True, 'message_id': msg.id, 'sender': request.user.username,
        'sender_avatar': request.user.avatar.url if request.user.avatar else '',
        'timestamp': timezone.localtime(msg.timestamp).strftime('%I:%M %p'),
        'file_url': msg.file.url, 'file_name': blob.name, 'file_type': 'voice', 'file_size': '',
    })


@login_required
@require_POST
def upload_group_voice_view(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if not group.members.filter(id=request.user.id).exists():
        return JsonResponse({'error': 'Not a member'}, status=403)
    blob = request.FILES.get('voice')
    if not blob: return JsonResponse({'error': 'No audio'}, status=400)
    ct = blob.content_type or 'audio/webm'
    ext = 'ogg' if 'ogg' in ct else 'webm'
    blob.name = f'voice_{uuid.uuid4().hex}.{ext}'
    msg = GroupMessage(group=group, sender=request.user, file_name=blob.name, file_type='voice')
    msg.set_message('')
    msg.file = blob
    msg.save()
    return JsonResponse({
        'ok': True, 'message_id': msg.id, 'sender': request.user.username,
        'sender_avatar': request.user.avatar.url if request.user.avatar else '',
        'timestamp': timezone.localtime(msg.timestamp).strftime('%I:%M %p'),
        'file_url': msg.file.url, 'file_name': blob.name, 'file_type': 'voice', 'file_size': '',
    })


# ── Admin Dashboard ─────────────────────────────────────────────────────────────
@login_required
def admin_dashboard_view(request):
    """Super admin dashboard — only accessible to superusers."""
    if not request.user.is_superuser:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('Access denied. Superuser required.')

    total_users      = User.objects.count()
    total_messages   = Message.objects.count()
    encrypted_msgs   = Message.objects.exclude(encrypted_content='').count()
    group_chats      = Group.objects.count()
    unread_messages  = Message.objects.filter(is_read=False).count()
    files_shared     = Message.objects.exclude(file='').count()

    # Recent 20 messages (decrypted for admin view)
    recent_messages = []
    for msg in Message.objects.select_related('sender','receiver').order_by('-timestamp')[:20]:
        try:
            content = msg.message_content if not msg.file else f'📎 {msg.file_name or "file"}'
        except Exception:
            content = '[encrypted]'
        try:
            receiver_username = msg.receiver.username if msg.receiver else '—'
        except Exception:
            receiver_username = '—'
        recent_messages.append({
            'sender':    msg.sender.username,
            'receiver':  receiver_username,
            'content':   content,
            'timestamp': timezone.localtime(msg.timestamp).strftime('%H:%M'),
            'encrypted': bool(msg.encrypted_content),
            'file_type': msg.file_type,
        })

    # Show ALL users (including those without email). Ghost 'None' user filtered in template.
    all_users = User.objects.all().values('username', 'email', 'is_active', 'date_joined').order_by('-date_joined')

    ctx = {
        'total_users':     total_users,
        'total_messages':  total_messages,
        'encrypted_msgs':  encrypted_msgs,
        'group_chats':     group_chats,
        'unread_messages': unread_messages,
        'files_shared':    files_shared,
        'recent_messages': recent_messages,
        'all_users':       all_users,
    }
    return render(request, 'chat/admin_dashboard.html', ctx)


# ── Admin Sub-Pages ──────────────────────────────────────────────────────────

def _admin_required(view_func):
    """Decorator: require superuser."""
    from functools import wraps
    from django.http import HttpResponseForbidden
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth import REDIRECT_FIELD_NAME
            from django.shortcuts import redirect as _redirect
            return _redirect(f'/users/login/?next={request.path}')
        if not request.user.is_superuser:
            return HttpResponseForbidden('Access denied. Superuser required.')
        return view_func(request, *args, **kwargs)
    return wrapper


@_admin_required
def admin_users_view(request):
    """Admin: full user list with search/filter."""
    query = request.GET.get('q', '').strip()
    users_qs = User.objects.all().order_by('-date_joined')
    if query:
        users_qs = users_qs.filter(
            Q(username__icontains=query) | Q(email__icontains=query)
        )
    ctx = {
        'users': users_qs,
        'query': query,
        'total': User.objects.count(),
        'active': User.objects.filter(is_active=True).count(),
        'staff': User.objects.filter(is_staff=True).count(),
    }
    return render(request, 'chat/admin_users.html', ctx)


@_admin_required
def admin_messages_view(request):
    """Admin: all DM messages."""
    query = request.GET.get('q', '').strip()
    msgs_qs = Message.objects.select_related('sender', 'receiver').order_by('-timestamp')
    if query:
        msgs_qs = msgs_qs.filter(
            Q(sender__username__icontains=query) | Q(receiver__username__icontains=query)
        )
    all_messages = []
    for msg in msgs_qs[:200]:
        try:
            content = msg.message_content if not msg.file else f'📎 {msg.file_name or "file"}'
        except Exception:
            content = '[encrypted]'
        all_messages.append({
            'id':        msg.id,
            'sender':    msg.sender.username,
            'receiver':  msg.receiver.username,
            'content':   content,
            'timestamp': timezone.localtime(msg.timestamp).strftime('%Y-%m-%d %H:%M'),
            'encrypted': bool(msg.encrypted_content),
            'file_type': msg.file_type,
            'is_read':   msg.is_read,
        })
    ctx = {
        'messages':   all_messages,
        'total':      Message.objects.count(),
        'unread':     Message.objects.filter(is_read=False).count(),
        'with_files': Message.objects.exclude(file='').count(),
        'query':      query,
    }
    return render(request, 'chat/admin_messages.html', ctx)


@_admin_required
def admin_groups_view(request):
    """Admin: all group chats."""
    groups = Group.objects.prefetch_related('members').select_related('created_by').order_by('-created_at')
    group_data = []
    for g in groups:
        group_data.append({
            'id':         g.id,
            'name':       g.name,
            'description': g.description,
            'created_by': g.created_by.username,
            'members':    g.members.count(),
            'messages':   GroupMessage.objects.filter(group=g).count(),
            'created_at': timezone.localtime(g.created_at).strftime('%Y-%m-%d'),
        })
    ctx = {
        'groups': group_data,
        'total':  Group.objects.count(),
    }
    return render(request, 'chat/admin_groups.html', ctx)


@_admin_required
def admin_group_messages_view(request):
    """Admin: all group messages."""
    query    = request.GET.get('q', '').strip()
    group_id = request.GET.get('group', '').strip()
    msgs_qs  = GroupMessage.objects.select_related('sender', 'group').order_by('-timestamp')
    if query:
        msgs_qs = msgs_qs.filter(
            Q(sender__username__icontains=query) | Q(group__name__icontains=query)
        )
    if group_id:
        msgs_qs = msgs_qs.filter(group_id=group_id)
    all_messages = []
    for msg in msgs_qs[:200]:
        try:
            content = msg.message_content if not msg.file else f'📎 {msg.file_name or "file"}'
        except Exception:
            content = '[encrypted]'
        all_messages.append({
            'id':        msg.id,
            'sender':    msg.sender.username,
            'group':     msg.group.name,
            'group_id':  msg.group.id,
            'content':   content,
            'timestamp': timezone.localtime(msg.timestamp).strftime('%Y-%m-%d %H:%M'),
            'file_type': msg.file_type,
        })
    groups = Group.objects.all().order_by('name')
    ctx = {
        'messages': all_messages,
        'total':    GroupMessage.objects.count(),
        'query':    query,
        'groups':   groups,
        'sel_group': group_id,
    }
    return render(request, 'chat/admin_group_messages.html', ctx)


@_admin_required
def admin_search_view(request):
    """Admin: search users by username/email."""
    query = request.GET.get('q', '').strip()
    results = []
    if query:
        users = User.objects.filter(
            Q(username__icontains=query) | Q(email__icontains=query)
        ).order_by('username')
        for u in users:
            sent = Message.objects.filter(sender=u).count()
            recv = Message.objects.filter(receiver=u).count()
            results.append({
                'username':   u.username,
                'email':      u.email,
                'is_active':  u.is_active,
                'is_staff':   u.is_staff,
                'date_joined': timezone.localtime(u.date_joined).strftime('%Y-%m-%d') if u.date_joined else '',
                'sent':       sent,
                'received':   recv,
                'groups':     u.group_memberships.count(),
            })
    ctx = {'query': query, 'results': results}
    return render(request, 'chat/admin_search.html', ctx)


# ── Admin User Management API ─────────────────────────────────────────────────

@_admin_required
@require_POST
def admin_add_user_view(request):
    """Admin: create a new user."""
    import json as _json
    try:
        data     = _json.loads(request.body)
        username = data.get('username', '').strip()
        email    = data.get('email', '').strip()
        password = data.get('password', '').strip()
        if not username or not password:
            return JsonResponse({'error': 'Username and password are required.'}, status=400)
        if User.objects.filter(username=username).exists():
            return JsonResponse({'error': f'Username "{username}" already exists.'}, status=400)
        if email and User.objects.filter(email=email).exists():
            return JsonResponse({'error': f'Email "{email}" already in use.'}, status=400)
        user = User.objects.create_user(username=username, email=email, password=password)
        return JsonResponse({'ok': True, 'username': user.username, 'email': user.email,
                             'date_joined': timezone.localtime(user.date_joined).strftime('%Y-%m-%d %H:%M')})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@_admin_required
@require_POST
def admin_delete_user_view(request, username):
    """Admin: permanently delete a user."""
    try:
        user = get_object_or_404(User, username=username)
        if user == request.user:
            return JsonResponse({'error': 'You cannot delete your own account.'}, status=400)
        user.delete()
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@_admin_required
@require_POST
def admin_toggle_user_view(request, username):
    """Admin: activate or deactivate a user."""
    try:
        user = get_object_or_404(User, username=username)
        if user == request.user:
            return JsonResponse({'error': 'You cannot deactivate your own account.'}, status=400)
        user.is_active = not user.is_active
        user.save(update_fields=['is_active'])
        return JsonResponse({'ok': True, 'is_active': user.is_active})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ── Message Delete API ─────────────────────────────────────────────────────────

@login_required
@require_POST
def delete_message_view(request, message_id):
    """Delete a single DM (only superuser/admin can delete)."""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Only admin can delete messages.'}, status=403)
    try:
        msg = get_object_or_404(Message, id=message_id)
        msg.delete()
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def delete_all_messages_view(request, username):
    """Delete all DMs between current user and other user (superuser only)."""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Only admin can delete all messages.'}, status=403)
    other = get_object_or_404(User, username=username)
    Message.objects.filter(
        Q(sender=request.user, receiver=other) |
        Q(sender=other, receiver=request.user)
    ).delete()
    return JsonResponse({'ok': True})


@login_required
@require_POST
def delete_group_message_view(request, message_id):
    """Delete a single group message (only superuser/admin can delete)."""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Only admin can delete messages.'}, status=403)
    try:
        msg = get_object_or_404(GroupMessage, id=message_id)
        msg.delete()
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def delete_all_group_messages_view(request, group_id):
    """Delete all messages in a group (superuser or group admin can do this)."""
    group = get_object_or_404(Group, id=group_id)
    if not request.user.is_superuser and group.created_by != request.user:
        return JsonResponse({'error': 'Only admin can clear all messages.'}, status=403)
    GroupMessage.objects.filter(group=group).delete()
    return JsonResponse({'ok': True})


@login_required
def poll_conversations_view(request):
    """
    Polling endpoint for the home page conversation list.
    Returns each conversation's last message preview, unread count, timestamp,
    and the last message_id — so the home page updates without a full refresh.
    """
    sent_to       = Message.objects.filter(sender=request.user).values_list('receiver', flat=True)
    received_from = Message.objects.filter(receiver=request.user).values_list('sender', flat=True)
    chatted_ids   = set(list(sent_to) + list(received_from))

    results = []
    for uid in chatted_ids:
        try:
            other = User.objects.get(pk=uid)
        except User.DoesNotExist:
            continue
        if other.is_superuser and not request.user.is_superuser:
            continue
        last = Message.objects.filter(
            Q(sender=request.user, receiver=other) |
            Q(sender=other, receiver=request.user)
        ).order_by('-timestamp').first()
        unread = Message.objects.filter(sender=other, receiver=request.user, is_read=False).count()
        avatar = other.avatar.url if other.avatar else ''

        if last:
            if last.file:
                preview = f'📎 {last.file_name or "file"}'
            else:
                preview = last.message_content[:50] if last.message_content else ''
            if last.sender == request.user:
                preview = 'You: ' + preview
            ts = timezone.localtime(last.timestamp).strftime('%I:%M %p')
            last_id = last.id
        else:
            preview = ''
            ts = ''
            last_id = 0

        results.append({
            'username': other.username,
            'avatar': avatar,
            'preview': preview,
            'timestamp': ts,
            'unread': unread,
            'last_id': last_id,
            'chat_url': f'/chat/room/{other.username}/',
        })

    # Sort by last_id descending (newest conversation first)
    results.sort(key=lambda x: x['last_id'], reverse=True)
    return JsonResponse({'conversations': results})


@login_required
def poll_new_messages_view(request, username):
    """
    Polling fallback for real-time messages.
    Returns all messages between current user and `username` with id > since_id.
    Used when WebSocket broadcast fails (e.g. Cloudflare tunnel / InMemoryChannelLayer).
    """
    since_id = int(request.GET.get('since', 0))
    other_user = get_object_or_404(User, username=username)
    msgs = Message.objects.filter(
        Q(sender=request.user, receiver=other_user) |
        Q(sender=other_user, receiver=request.user),
        id__gt=since_id
    ).order_by('id')

    results = []
    for msg in msgs:
        avatar = msg.sender.avatar.url if msg.sender.avatar else ''
        ts = timezone.localtime(msg.timestamp).strftime('%I:%M %p')
        entry = {
            'message_id': msg.id,
            'sender': msg.sender.username,
            'sender_avatar': avatar,
            'timestamp': ts,
            'file_message': bool(msg.file),
        }
        if msg.file:
            entry['file_url'] = msg.file.url
            entry['file_name'] = msg.file_name or ''
            entry['file_type'] = msg.file_type or 'document'
            entry['file_size'] = format_size(msg.file.size) if msg.file else ''
            entry['message'] = ''
        else:
            entry['message'] = msg.message_content
        results.append(entry)

    return JsonResponse({'messages': results})


@login_required
def poll_new_group_messages_view(request, group_id):
    """Polling fallback for group chat real-time messages."""
    since_id = int(request.GET.get('since', 0))
    group = get_object_or_404(Group, id=group_id)
    if not group.members.filter(id=request.user.id).exists():
        return JsonResponse({'error': 'Not a member'}, status=403)

    msgs = GroupMessage.objects.filter(
        group=group,
        id__gt=since_id
    ).order_by('id')

    results = []
    for msg in msgs:
        avatar = msg.sender.avatar.url if msg.sender.avatar else ''
        ts = timezone.localtime(msg.timestamp).strftime('%I:%M %p')
        entry = {
            'message_id': msg.id,
            'sender': msg.sender.username,
            'sender_avatar': avatar,
            'timestamp': ts,
            'file_message': bool(msg.file),
        }
        if msg.file:
            entry['file_url'] = msg.file.url
            entry['file_name'] = msg.file_name or ''
            entry['file_type'] = msg.file_type or 'document'
            entry['file_size'] = format_size(msg.file.size) if msg.file else ''
            entry['message'] = ''
        else:
            entry['message'] = msg.message_content
        results.append(entry)

    return JsonResponse({'messages': results})
