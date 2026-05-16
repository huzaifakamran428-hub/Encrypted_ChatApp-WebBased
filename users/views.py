import random
import string
from datetime import timedelta

from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings as django_settings
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .forms import RegisterForm, LoginForm, AvatarForm
from .models import CustomUser


def _generate_otp():
    return ''.join(random.choices(string.digits, k=4))


def register_view(request):
    if request.user.is_authenticated:
        return redirect('chat:home')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            email    = form.cleaned_data['email']
            password = form.cleaned_data['password1']

            # Email OTP must have been verified for this exact email address
            verified_email = request.session.get('email_otp_verified')
            if verified_email != email:
                messages.error(request, 'Please verify your email address before creating your account.')
                return render(request, 'users/register.html', {'form': form})

            try:
                user = CustomUser.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                )
                for k in ('email_otp_code', 'email_otp_expiry', 'email_otp_email', 'email_otp_verified'):
                    request.session.pop(k, None)
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                messages.success(request, f'Welcome, {user.username}! Your account has been created.')
                return redirect('chat:home')
            except Exception as e:
                messages.error(request, f'Account creation failed: {str(e)}. Please try again.')
                return render(request, 'users/register.html', {'form': form})
    else:
        form = RegisterForm()
    return render(request, 'users/register.html', {'form': form})


@require_POST
def send_email_otp_view(request):
    """AJAX — generate a 4-digit OTP, email it to the user, store in session."""
    import json
    try:
        data  = json.loads(request.body)
        email = (data.get('email') or '').strip()
    except Exception:
        email = request.POST.get('email', '').strip()

    if not email:
        return JsonResponse({'ok': False, 'error': 'Email address is required.'})

    if CustomUser.objects.filter(email=email).exists():
        return JsonResponse({'ok': False, 'error': 'An account with this email already exists.'})

    otp    = _generate_otp()
    expiry = (timezone.now() + timedelta(minutes=django_settings.OTP_EXPIRY_MINUTES)).isoformat()

    # Store in session — reset verified flag so a new code always invalidates old verification
    request.session['email_otp_code']     = otp
    request.session['email_otp_expiry']   = expiry
    request.session['email_otp_email']    = email
    request.session['email_otp_verified'] = None

    try:
        send_mail(
            subject='Your ChatApp Verification Code',
            message=(
                f'Your ChatApp email verification code is: {otp}\n\n'
                f'Enter this code on the registration page to verify your email.\n'
                f'This code expires in {django_settings.OTP_EXPIRY_MINUTES} minutes.\n\n'
                f'If you did not request this, please ignore this email.\n\n'
                f'— ChatApp Team'
            ),
            html_message=f'''
            <div style="font-family:'Segoe UI',sans-serif;max-width:460px;margin:auto;
                        background:#0f0f13;color:#e8e8f0;padding:40px 36px;
                        border-radius:16px;border:1px solid #2e2e42;">
                <div style="text-align:center;margin-bottom:28px;">
                    <div style="display:inline-flex;align-items:center;gap:10px;">
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="38" height="38" style="display:inline-block;vertical-align:middle;">
                            <circle cx="50" cy="50" r="50" fill="#7c6af7"/>
                            <path d="M50 18 C30 18 15 31 15 47 C15 57 21 65.5 31 70.5 L28 82 L42 74.5 C44.5 75 47.2 75.2 50 75.2 C70 75.2 85 62.2 85 47 C85 31 70 18 50 18 Z" fill="white"/>
                            <circle cx="35" cy="47" r="5" fill="#7c6af7"/>
                            <circle cx="50" cy="47" r="5" fill="#7c6af7"/>
                            <circle cx="65" cy="47" r="5" fill="#7c6af7"/>
                        </svg>
                        <span style="font-size:1.6rem;font-weight:800;color:#7c6af7;vertical-align:middle;">ChatApp</span>
                    </div>
                </div>
                <h2 style="font-size:1.1rem;font-weight:700;margin-bottom:6px;color:#e8e8f0;">
                    Verify your email address
                </h2>
                <p style="color:#9090a8;font-size:0.9rem;margin-bottom:24px;">
                    Enter the code below on the registration page to verify
                    <strong style="color:#7c6af7;">{email}</strong>
                </p>
                <div style="background:#22222f;border:2px solid #7c6af7;border-radius:14px;
                            padding:28px;text-align:center;margin-bottom:24px;">
                    <p style="color:#9090a8;font-size:0.78rem;margin-bottom:10px;
                               letter-spacing:0.05em;text-transform:uppercase;">
                        Your verification code
                    </p>
                    <div style="letter-spacing:18px;font-size:2.6rem;font-weight:900;
                                color:#7c6af7;font-variant-numeric:tabular-nums;">
                        {otp}
                    </div>
                </div>
                <p style="color:#5c5c78;font-size:0.78rem;text-align:center;">
                    Expires in <strong style="color:#9090a8;">
                    {django_settings.OTP_EXPIRY_MINUTES} minutes</strong>.
                    If you did not request this, ignore this email.
                </p>
            </div>
            ''',
            from_email=django_settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
        return JsonResponse({'ok': True, 'message': f'Verification code sent to {email}'})

    except Exception as exc:
        # Clear the session so a stale code is never silently accepted
        for k in ('email_otp_code', 'email_otp_expiry', 'email_otp_email'):
            request.session.pop(k, None)
        import logging
        logging.getLogger(__name__).error('Email send failed: %s', exc)
        return JsonResponse({
            'ok': False,
            'error': f'Could not send email: {exc}'
        })


@require_POST
def verify_email_otp_view(request):
    """AJAX — validate the OTP the user typed; mark email as verified in session."""
    import json
    try:
        data  = json.loads(request.body)
        code  = (data.get('code') or '').strip()
        email = (data.get('email') or '').strip()
    except Exception:
        code  = request.POST.get('code', '').strip()
        email = request.POST.get('email', '').strip()

    stored_otp   = request.session.get('email_otp_code', '')
    stored_email = request.session.get('email_otp_email', '')
    otp_expiry   = request.session.get('email_otp_expiry', '')

    if not stored_otp or not stored_email:
        return JsonResponse({'ok': False, 'error': 'No code found. Please request a new code first.'})

    if email != stored_email:
        return JsonResponse({'ok': False, 'error': 'Email mismatch. Please request a new code.'})

    if otp_expiry:
        from django.utils.dateparse import parse_datetime
        expiry_dt = parse_datetime(otp_expiry)
        if expiry_dt and timezone.now() > expiry_dt:
            return JsonResponse({'ok': False, 'error': 'Code expired. Please request a new one.'})

    if code == stored_otp:
        request.session['email_otp_verified'] = email
        return JsonResponse({'ok': True})

    return JsonResponse({'ok': False, 'error': 'Incorrect code. Please try again.'})


def verify_otp_view(request):
    pending = request.session.get('pending_registration')
    if not pending:
        messages.error(request, 'Registration session expired. Please start again.')
        return redirect('users:register')
    if request.method == 'POST':
        entered_otp = ''.join([
            request.POST.get('otp1', ''),
            request.POST.get('otp2', ''),
            request.POST.get('otp3', ''),
            request.POST.get('otp4', ''),
        ]).strip()
        stored_otp = request.session.get('otp_code', '')
        otp_expiry = request.session.get('otp_expiry', '')
        if otp_expiry:
            from django.utils.dateparse import parse_datetime
            expiry_dt = parse_datetime(otp_expiry)
            if expiry_dt and timezone.now() > expiry_dt:
                messages.error(request, 'Verification code expired. Please register again.')
                _clear_otp_session(request)
                return redirect('users:register')
        if entered_otp == stored_otp:
            try:
                if CustomUser.objects.filter(username=pending['username']).exists():
                    _clear_otp_session(request)
                    messages.error(request, f'Username "{pending["username"]}" was just taken.')
                    return redirect('users:register')
                if CustomUser.objects.filter(email=pending['email']).exists():
                    _clear_otp_session(request)
                    messages.error(request, f'Email "{pending["email"]}" is already registered.')
                    return redirect('users:login')
                user = CustomUser.objects.create_user(
                    username=pending['username'],
                    email=pending['email'],
                    password=pending['password'],
                )
                _clear_otp_session(request)
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                messages.success(request, f'Welcome, {user.username}!')
                return redirect('chat:home')
            except Exception as e:
                messages.error(request, f'Account creation failed: {str(e)}.')
                _clear_otp_session(request)
                return redirect('users:register')
        else:
            messages.error(request, 'Incorrect verification code.')
    email = request.session.get('otp_email', '')
    return render(request, 'users/verify_otp.html', {'email': email})


def resend_otp_view(request):
    pending = request.session.get('pending_registration')
    if not pending:
        return JsonResponse({'error': 'Session expired'}, status=400)
    otp    = _generate_otp()
    expiry = (timezone.now() + timedelta(minutes=django_settings.OTP_EXPIRY_MINUTES)).isoformat()
    request.session['otp_code']   = otp
    request.session['otp_expiry'] = expiry
    try:
        send_mail(
            subject='Your ChatApp Verification Code (Resent)',
            message=f'Your new code is: {otp}. Expires in {django_settings.OTP_EXPIRY_MINUTES} minutes.',
            from_email=django_settings.DEFAULT_FROM_EMAIL,
            recipient_list=[pending['email']],
            fail_silently=True,
        )
        return JsonResponse({'ok': True, 'message': f'New code sent to {pending["email"]}'})
    except Exception:
        return JsonResponse({'ok': False, 'message': 'Failed to resend. Please try again.'})


def _clear_otp_session(request):
    for k in ('pending_registration', 'otp_code', 'otp_expiry', 'otp_email'):
        request.session.pop(k, None)


def login_view(request):
    if request.user.is_authenticated:
        return redirect('chat:home')
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f'Welcome back, {user.username}!')
            next_url = request.GET.get('next', 'chat:home')
            return redirect(next_url)
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = LoginForm()
    return render(request, 'users/login.html', {'form': form})


@login_required
def logout_view(request):
    if request.method == 'POST':
        logout(request)
        messages.success(request, 'You have been logged out successfully.')
        return redirect('users:login')
    return render(request, 'users/logout_confirm.html')


@login_required
def profile_view(request):
    if request.method == 'POST':
        form = AvatarForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated!')
            return redirect('users:profile')
    else:
        form = AvatarForm(instance=request.user)
    return render(request, 'users/profile.html', {'user': request.user, 'form': form})
