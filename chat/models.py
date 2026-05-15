"""
Models for ChatApp — with AES-256 encryption (Information Security Project)

Message Table (from SRS Data Requirements):
  - id                (PK)
  - sender_id         (FK → User)
  - receiver_id       (FK → User)
  - message_content   (plaintext — only in memory, never persisted directly)
  - encrypted_content (AES-256-CBC ciphertext, base64)
  - encryption_iv     (IV for this message, base64)
  - timestamp         (DateTime)

File Table (from SRS 3.3):
  - encrypted_file_path  (AES-encrypted path, base64)
  - encryption_iv        (IV, base64)
"""

from django.db import models
from django.conf import settings
import os
from .encryption import encrypt_message, decrypt_message


def message_file_path(instance, filename):
    return f'chat_files/{instance.sender.username}/{filename}'


def group_icon_path(instance, filename):
    ext = filename.rsplit('.', 1)[-1]
    return f'group_icons/{instance.id}.{ext}'


class Group(models.Model):
    name        = models.CharField(max_length=100)
    description = models.TextField(blank=True, max_length=300)
    icon        = models.ImageField(upload_to=group_icon_path, blank=True, null=True)
    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='created_groups', on_delete=models.CASCADE)
    members     = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name='group_memberships', blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def get_icon_url(self):
        return self.icon.url if self.icon else None


class GroupMessage(models.Model):
    group           = models.ForeignKey(Group, related_name='messages', on_delete=models.CASCADE)
    sender          = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='group_messages_sent', on_delete=models.CASCADE)
    # Encrypted storage
    encrypted_content = models.TextField(blank=True)
    encryption_iv     = models.CharField(max_length=64, blank=True)
    # File attachment
    file      = models.FileField(upload_to='group_files/', blank=True, null=True)
    file_name = models.CharField(max_length=255, blank=True)
    file_type = models.CharField(max_length=50, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def set_message(self, plaintext: str):
        """Encrypt and store message."""
        ct, iv = encrypt_message(plaintext)
        self.encrypted_content = ct
        self.encryption_iv = iv

    def get_message(self) -> str:
        """Decrypt and return plaintext."""
        return decrypt_message(self.encrypted_content, self.encryption_iv)

    @property
    def message_content(self):
        return self.get_message()

    def __str__(self):
        return f'[{self.group.name}] {self.sender.username}: {self.get_message()[:40]}'


class Message(models.Model):
    """
    1-on-1 Message — AES-256 encrypted storage.

    SRS Data Requirements (Section 3.3):
      - sender_id         FK → User
      - receiver_id       FK → User
      - message_content   (plaintext accessor — decrypts on read)
      - encrypted_content (AES-256-CBC ciphertext stored in DB)
      - encryption_iv     (unique IV per message)
      - timestamp
    """
    sender   = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='sent_messages', on_delete=models.CASCADE)
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='received_messages', on_delete=models.CASCADE)

    # ── Encrypted fields (what actually gets stored in the DB) ──
    encrypted_content = models.TextField(blank=True)
    encryption_iv     = models.CharField(max_length=64, blank=True)

    # ── File attachment ──
    file      = models.FileField(upload_to=message_file_path, blank=True, null=True)
    file_name = models.CharField(max_length=255, blank=True)
    file_type = models.CharField(max_length=50, blank=True)

    # ── File encryption (SRS File Table) ──
    encrypted_file_path = models.TextField(blank=True)
    file_iv             = models.CharField(max_length=64, blank=True)

    timestamp = models.DateTimeField(auto_now_add=True)
    is_read   = models.BooleanField(default=False)

    class Meta:
        ordering = ['timestamp']
        indexes  = [
            models.Index(fields=['sender', 'receiver']),
            models.Index(fields=['timestamp']),
        ]

    # ── Encryption helpers ──
    def set_message(self, plaintext: str):
        """Encrypt plaintext and store in encrypted_content + encryption_iv."""
        ct, iv = encrypt_message(plaintext)
        self.encrypted_content = ct
        self.encryption_iv = iv

    def get_message(self) -> str:
        """Decrypt encrypted_content and return plaintext."""
        return decrypt_message(self.encrypted_content, self.encryption_iv)

    @property
    def message_content(self):
        """Transparent property — always returns decrypted plaintext."""
        return self.get_message()

    def __str__(self):
        return f'{self.sender.username} → {self.receiver.username}: {self.get_message()[:40]}'
