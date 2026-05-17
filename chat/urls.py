from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    path('', views.home_view, name='home'),
    path('help/', views.help_view, name='help'),
    path('room/<str:username>/', views.chat_room_view, name='room'),
    path('search/', views.search_users_view, name='search'),
    path('send/', views.send_message_view, name='send'),
    path('upload/', views.upload_file_view, name='upload'),
    path('upload/voice/', views.upload_voice_view, name='upload_voice'),
    path('group/create/', views.create_group_view, name='create_group'),
    path('group/<int:group_id>/', views.group_room_view, name='group_room'),
    path('group/<int:group_id>/upload/', views.group_upload_file_view, name='group_upload'),
    path('group/<int:group_id>/upload/voice/', views.upload_group_voice_view, name='group_upload_voice'),
    path('group/<int:group_id>/add-member/', views.add_member_view, name='add_member'),
    path('group/<int:group_id>/leave/', views.leave_group_view, name='leave_group'),
    path('admin-panel/', views.admin_dashboard_view, name='admin_dashboard'),
    # Admin sub-pages
    path('admin-panel/users/', views.admin_users_view, name='admin_users'),
    path('admin-panel/messages/', views.admin_messages_view, name='admin_messages'),
    path('admin-panel/groups/', views.admin_groups_view, name='admin_groups'),
    path('admin-panel/group-messages/', views.admin_group_messages_view, name='admin_group_messages'),
    path('admin-panel/search/', views.admin_search_view, name='admin_search'),
    # Admin user management API
    path('admin-panel/users/add/', views.admin_add_user_view, name='admin_add_user'),
    path('admin-panel/users/<str:username>/delete/', views.admin_delete_user_view, name='admin_delete_user'),
    path('admin-panel/users/<str:username>/toggle/', views.admin_toggle_user_view, name='admin_toggle_user'),
    # NEW: Reset password & set role
    path('admin-panel/users/<str:username>/reset-password/', views.admin_reset_password_view, name='admin_reset_password'),
    path('admin-panel/users/<str:username>/set-role/', views.admin_set_role_view, name='admin_set_role'),
    # Message delete API
    path('message/<int:message_id>/delete/', views.delete_message_view, name='delete_message'),
    path('messages/delete-all/<str:username>/', views.delete_all_messages_view, name='delete_all_messages'),
    path('group-message/<int:message_id>/delete/', views.delete_group_message_view, name='delete_group_message'),
    path('group/<int:group_id>/messages/delete-all/', views.delete_all_group_messages_view, name='delete_all_group_messages'),
    # Polling fallback for real-time messages (WebSocket backup)
    path('poll/conversations/', views.poll_conversations_view, name='poll_conversations'),
    path('poll/<str:username>/', views.poll_new_messages_view, name='poll_messages'),
    path('group/<int:group_id>/poll/', views.poll_new_group_messages_view, name='poll_group_messages'),
]
