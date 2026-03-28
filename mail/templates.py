from __future__ import annotations

from html import escape

# ---------- shared layout ----------

_STYLE = """
<style>
    body { margin: 0; padding: 0; background-color: #f4f5f7; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }
    .container { max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 8px; overflow: hidden; }
    .header { background: #0A84FF; padding: 32px 40px; }
    .header h1 { color: #ffffff; margin: 0; font-size: 22px; font-weight: 600; }
    .body { padding: 32px 40px; color: #1a1a2e; line-height: 1.6; }
    .body h2 { color: #0A84FF; font-size: 18px; margin-top: 0; }
    .body p { margin: 0 0 16px 0; font-size: 14px; }
    .cred-box { background: #f0f4ff; border: 1px solid #d0dcf0; border-radius: 6px; padding: 16px 20px; margin: 20px 0; }
    .cred-box p { margin: 4px 0; font-size: 14px; }
    .cred-label { color: #666; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
    .cred-value { font-weight: 600; color: #1a1a2e; font-family: 'Courier New', monospace; font-size: 15px; }
    .btn { display: inline-block; background: #0A84FF; color: #ffffff !important; text-decoration: none; padding: 12px 28px; border-radius: 6px; font-weight: 600; font-size: 14px; margin: 8px 0; }
    .footer { padding: 24px 40px; background: #f8f9fa; border-top: 1px solid #e9ecef; text-align: center; }
    .footer p { margin: 0; font-size: 12px; color: #999; }
    .alert-box { border-radius: 6px; padding: 16px 20px; margin: 20px 0; }
    .alert-critical { background: #fff0f2; border: 1px solid #ffcdd2; }
    .alert-warning { background: #fff8e1; border: 1px solid #ffe082; }
    .badge { display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }
    .badge-red { background: #FF3B5C; color: #fff; }
    .badge-amber { background: #F5A623; color: #fff; }
    .badge-green { background: #00A86B; color: #fff; }
    .stat-grid { display: flex; gap: 12px; margin: 20px 0; }
    .stat-card { flex: 1; background: #f8f9fa; border-radius: 6px; padding: 16px; text-align: center; }
    .stat-number { font-size: 28px; font-weight: 700; color: #0A84FF; }
    .stat-label { font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 4px; }
    table { width: 100%; border-collapse: collapse; margin: 16px 0; }
    th { background: #f0f4ff; text-align: left; padding: 10px 12px; font-size: 12px; color: #666; text-transform: uppercase; letter-spacing: 0.5px; }
    td { padding: 10px 12px; font-size: 14px; border-bottom: 1px solid #f0f0f0; }
</style>
"""


def _wrap(title: str, body: str) -> str:
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">{_STYLE}</head>
<body style="margin:0;padding:20px 0;background:#f4f5f7;">
<div class="container">
    <div class="header"><h1>{escape(title)}</h1></div>
    <div class="body">{body}</div>
    <div class="footer"><p>Fayol Solutions &mdash; Professional Services Management</p><p>This is an automated message. Please do not reply directly to this email.</p></div>
</div>
</body>
</html>"""


# ---------- 1. Welcome email ----------

def welcome_email(
    user_name: str,
    email: str,
    temp_password: str,
    tenant_name: str,
    login_url: str,
) -> tuple[str, str]:
    """Returns (subject, html_body)."""
    subject = f"Welcome to Fayol — {tenant_name}"
    body = f"""\
<h2>Welcome, {escape(user_name)}!</h2>
<p>Your account has been created for <strong>{escape(tenant_name)}</strong> on the Fayol platform. Below are your login credentials.</p>
<div class="cred-box">
    <p class="cred-label">Email</p>
    <p class="cred-value">{escape(email)}</p>
    <p class="cred-label" style="margin-top:12px;">Temporary Password</p>
    <p class="cred-value">{escape(temp_password)}</p>
</div>
<p><a class="btn" href="{escape(login_url)}">Sign In to Fayol</a></p>
<p style="color:#e53e3e;font-weight:600;">Please change your password immediately after your first login.</p>
<p>If you did not expect this email or have questions, please contact your administrator.</p>"""
    return subject, _wrap("Welcome to Fayol", body)


# ---------- 2. Password reset email ----------

def password_reset_email(
    user_name: str,
    temp_password: str,
    login_url: str,
) -> tuple[str, str]:
    """Returns (subject, html_body)."""
    subject = "Fayol — Your Password Has Been Reset"
    body = f"""\
<h2>Password Reset</h2>
<p>Hi {escape(user_name)}, your password has been reset by an administrator. Please use the temporary password below to log in.</p>
<div class="cred-box">
    <p class="cred-label">Temporary Password</p>
    <p class="cred-value">{escape(temp_password)}</p>
</div>
<p><a class="btn" href="{escape(login_url)}">Sign In to Fayol</a></p>
<p style="color:#e53e3e;font-weight:600;">Please change your password immediately after logging in.</p>
<p>If you did not request this reset, contact your administrator immediately.</p>"""
    return subject, _wrap("Password Reset", body)


# ---------- 3. SLA escalation email ----------

def escalation_email(
    client_name: str,
    ticket_id: str,
    ticket_subject: str,
    priority: str,
    sla_status: str,
    breached_metric: str,
    assigned_to: str,
    escalation_contacts: list[str],
) -> tuple[str, str]:
    """Returns (subject, html_body)."""
    subject = f"[ESCALATION] SLA Breach — {ticket_id}: {ticket_subject}"

    priority_class = "badge-red" if priority.lower() in ("critical", "high") else "badge-amber"
    alert_class = "alert-critical" if "breach" in sla_status.lower() else "alert-warning"

    contacts_html = "".join(f"<li>{escape(c)}</li>" for c in escalation_contacts)

    body = f"""\
<h2>SLA Breach Escalation</h2>
<div class="{alert_class} alert-box">
    <p style="margin:0;font-weight:600;">An SLA breach has been detected that requires immediate attention.</p>
</div>
<table>
    <tr><th style="width:35%;">Field</th><th>Details</th></tr>
    <tr><td><strong>Client</strong></td><td>{escape(client_name)}</td></tr>
    <tr><td><strong>Ticket</strong></td><td>{escape(ticket_id)} &mdash; {escape(ticket_subject)}</td></tr>
    <tr><td><strong>Priority</strong></td><td><span class="badge {priority_class}">{escape(priority)}</span></td></tr>
    <tr><td><strong>SLA Status</strong></td><td>{escape(sla_status)}</td></tr>
    <tr><td><strong>Breached Metric</strong></td><td>{escape(breached_metric)}</td></tr>
    <tr><td><strong>Assigned To</strong></td><td>{escape(assigned_to)}</td></tr>
</table>
<p><strong>Escalation Contacts:</strong></p>
<ul>{contacts_html}</ul>
<p style="font-weight:600;">Please review this ticket and take corrective action as soon as possible.</p>"""
    return subject, _wrap("SLA Breach Escalation", body)


# ---------- 4. Weekly digest email ----------

def weekly_digest_email(
    client_name: str,
    period: str,
    open_tickets: int,
    closed_tickets: int,
    sla_percentage: float,
    breached_tickets: list[dict],
    upcoming_milestones: list[dict],
) -> tuple[str, str]:
    """Returns (subject, html_body).

    breached_tickets: list of {"ticket_id": ..., "subject": ..., "metric": ...}
    upcoming_milestones: list of {"name": ..., "due_date": ..., "status": ...}
    """
    subject = f"Fayol Weekly Digest — {client_name} ({period})"

    sla_color = "#00A86B" if sla_percentage >= 95 else "#F5A623" if sla_percentage >= 85 else "#FF3B5C"

    # Breached tickets table
    if breached_tickets:
        breach_rows = "".join(
            f'<tr><td>{escape(str(t.get("ticket_id", "")))}</td><td>{escape(str(t.get("subject", "")))}</td><td>{escape(str(t.get("metric", "")))}</td></tr>'
            for t in breached_tickets
        )
        breach_section = f"""\
<h3 style="color:#FF3B5C;">Breached Tickets</h3>
<table>
    <tr><th>Ticket</th><th>Subject</th><th>Metric</th></tr>
    {breach_rows}
</table>"""
    else:
        breach_section = '<p style="color:#00A86B;font-weight:600;">No SLA breaches this period.</p>'

    # Milestones table
    if upcoming_milestones:
        milestone_rows = "".join(
            f'<tr><td>{escape(str(m.get("name", "")))}</td><td>{escape(str(m.get("due_date", "")))}</td><td>{escape(str(m.get("status", "")))}</td></tr>'
            for m in upcoming_milestones
        )
        milestone_section = f"""\
<h3>Upcoming Milestones</h3>
<table>
    <tr><th>Milestone</th><th>Due Date</th><th>Status</th></tr>
    {milestone_rows}
</table>"""
    else:
        milestone_section = ""

    body = f"""\
<h2>Weekly Status Report</h2>
<p>Here is the weekly summary for <strong>{escape(client_name)}</strong> covering <strong>{escape(period)}</strong>.</p>

<!--[if mso]><table role="presentation" width="100%"><tr><td width="33%"><![endif]-->
<div style="display:inline-block;width:30%;min-width:150px;vertical-align:top;text-align:center;background:#f8f9fa;border-radius:6px;padding:16px;margin:6px;">
    <div style="font-size:28px;font-weight:700;color:#0A84FF;">{open_tickets}</div>
    <div style="font-size:11px;color:#888;text-transform:uppercase;letter-spacing:0.5px;margin-top:4px;">Open Tickets</div>
</div>
<!--[if mso]></td><td width="33%"><![endif]-->
<div style="display:inline-block;width:30%;min-width:150px;vertical-align:top;text-align:center;background:#f8f9fa;border-radius:6px;padding:16px;margin:6px;">
    <div style="font-size:28px;font-weight:700;color:#00A86B;">{closed_tickets}</div>
    <div style="font-size:11px;color:#888;text-transform:uppercase;letter-spacing:0.5px;margin-top:4px;">Closed Tickets</div>
</div>
<!--[if mso]></td><td width="33%"><![endif]-->
<div style="display:inline-block;width:30%;min-width:150px;vertical-align:top;text-align:center;background:#f8f9fa;border-radius:6px;padding:16px;margin:6px;">
    <div style="font-size:28px;font-weight:700;color:{sla_color};">{sla_percentage:.1f}%</div>
    <div style="font-size:11px;color:#888;text-transform:uppercase;letter-spacing:0.5px;margin-top:4px;">SLA Compliance</div>
</div>
<!--[if mso]></td></tr></table><![endif]-->

{breach_section}
{milestone_section}
<p style="margin-top:24px;font-size:13px;color:#888;">This report was automatically generated by the Fayol platform.</p>"""
    return subject, _wrap(f"Weekly Digest — {client_name}", body)
