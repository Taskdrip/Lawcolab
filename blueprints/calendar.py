from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user
from app import db
from models import (CalendarEvent, CalendarEventAttendee, Project, ProjectAssignment, User,
                    EVENT_TYPE_COURT, EVENT_TYPE_MEETING, EVENT_TYPE_APPOINTMENT,
                    EVENT_TYPE_DEADLINE, EVENT_TYPE_OTHER,
                    EVENT_STATUS_UPCOMING, EVENT_STATUS_COMPLETED, EVENT_STATUS_CANCELLED)
from utils.decorators import simple_login_required
from datetime import datetime, date, timedelta
import calendar as cal_module

calendar_bp = Blueprint('calendar', __name__)

EVENT_TYPES = [
    (EVENT_TYPE_COURT, 'Court Date'),
    (EVENT_TYPE_MEETING, 'Meeting'),
    (EVENT_TYPE_APPOINTMENT, 'Appointment'),
    (EVENT_TYPE_DEADLINE, 'Deadline'),
    (EVENT_TYPE_OTHER, 'Other'),
]

EVENT_STATUSES = [
    (EVENT_STATUS_UPCOMING, 'Upcoming'),
    (EVENT_STATUS_COMPLETED, 'Completed'),
    (EVENT_STATUS_CANCELLED, 'Cancelled'),
]

REMINDER_OPTIONS = [
    (0, 'At event time'),
    (15, '15 minutes before'),
    (30, '30 minutes before'),
    (60, '1 hour before'),
    (120, '2 hours before'),
    (1440, '1 day before'),
    (2880, '2 days before'),
    (10080, '1 week before'),
]


def get_firm_events_query():
    """Base query for events visible to the current user."""
    if current_user.is_super_admin():
        return CalendarEvent.query
    q = CalendarEvent.query.filter_by(law_firm_id=current_user.law_firm_id)
    if current_user.is_client():
        # Clients only see events they are attendees of
        q = q.join(CalendarEventAttendee).filter(CalendarEventAttendee.user_id == current_user.id)
    return q


def get_firm_projects():
    if current_user.is_admin() or current_user.is_super_admin():
        return Project.query.filter_by(law_firm_id=current_user.law_firm_id).all()
    return (Project.query
            .filter_by(law_firm_id=current_user.law_firm_id)
            .join(ProjectAssignment)
            .filter(ProjectAssignment.user_id == current_user.id)
            .all())


def get_firm_users():
    if not current_user.law_firm_id:
        return []
    return (User.query
            .filter_by(law_firm_id=current_user.law_firm_id, active=True)
            .all())


@calendar_bp.route('/')
@simple_login_required
def index():
    today = date.today()
    year = request.args.get('year', today.year, type=int)
    month = request.args.get('month', today.month, type=int)
    view = request.args.get('view', 'month')

    # Clamp month
    if month < 1:
        month = 12
        year -= 1
    elif month > 12:
        month = 1
        year += 1

    # Month boundaries
    first_day = datetime(year, month, 1)
    last_day_num = cal_module.monthrange(year, month)[1]
    last_day = datetime(year, month, last_day_num, 23, 59, 59)

    # Events for this month
    events = (get_firm_events_query()
              .filter(CalendarEvent.start_datetime >= first_day,
                      CalendarEvent.start_datetime <= last_day)
              .order_by(CalendarEvent.start_datetime)
              .all())

    # Upcoming events (next 7 days) for sidebar
    upcoming = (get_firm_events_query()
                .filter(CalendarEvent.start_datetime >= datetime.now(),
                        CalendarEvent.status == EVENT_STATUS_UPCOMING)
                .order_by(CalendarEvent.start_datetime)
                .limit(10)
                .all())

    # Build calendar grid
    cal = cal_module.monthcalendar(year, month)

    # Map day -> events
    events_by_day = {}
    for ev in events:
        d = ev.start_datetime.day
        events_by_day.setdefault(d, []).append(ev)

    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    month_name = first_day.strftime('%B %Y')

    return render_template('calendar/index.html',
                           cal=cal,
                           events=events,
                           events_by_day=events_by_day,
                           upcoming=upcoming,
                           year=year, month=month,
                           month_name=month_name,
                           today=today,
                           prev_month=prev_month, prev_year=prev_year,
                           next_month=next_month, next_year=next_year,
                           view=view)


@calendar_bp.route('/create', methods=['GET', 'POST'])
@simple_login_required
def create_event():
    if current_user.is_client():
        abort(403)

    projects = get_firm_projects()
    firm_users = get_firm_users()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Title is required.', 'danger')
            return render_template('calendar/create.html',
                                   event_types=EVENT_TYPES,
                                   reminder_options=REMINDER_OPTIONS,
                                   projects=projects,
                                   firm_users=firm_users)

        start_str = request.form.get('start_datetime', '')
        end_str = request.form.get('end_datetime', '')

        try:
            start_dt = datetime.strptime(start_str, '%Y-%m-%dT%H:%M')
        except (ValueError, TypeError):
            flash('Invalid start date/time.', 'danger')
            return render_template('calendar/create.html',
                                   event_types=EVENT_TYPES,
                                   reminder_options=REMINDER_OPTIONS,
                                   projects=projects,
                                   firm_users=firm_users)

        end_dt = None
        if end_str:
            try:
                end_dt = datetime.strptime(end_str, '%Y-%m-%dT%H:%M')
            except (ValueError, TypeError):
                end_dt = None

        event = CalendarEvent()
        event.title = title
        event.description = request.form.get('description', '').strip()
        event.event_type = request.form.get('event_type', EVENT_TYPE_MEETING)
        event.status = EVENT_STATUS_UPCOMING
        event.start_datetime = start_dt
        event.end_datetime = end_dt
        event.all_day = 'all_day' in request.form
        event.location = request.form.get('location', '').strip()
        event.virtual_link = request.form.get('virtual_link', '').strip()
        event.notes = request.form.get('notes', '').strip()
        event.law_firm_id = current_user.law_firm_id
        event.created_by_id = current_user.id

        proj_id = request.form.get('project_id', '')
        if proj_id:
            try:
                event.project_id = int(proj_id)
            except ValueError:
                event.project_id = None

        reminder_str = request.form.get('reminder_minutes', '60')
        try:
            event.reminder_minutes = int(reminder_str)
        except ValueError:
            event.reminder_minutes = 60

        db.session.add(event)
        db.session.flush()

        # Add attendees
        attendee_ids = request.form.getlist('attendee_ids')
        for uid in attendee_ids:
            if uid != current_user.id:
                att = CalendarEventAttendee(event_id=event.id, user_id=uid)
                db.session.add(att)
        # Always add creator
        creator_att = CalendarEventAttendee(event_id=event.id, user_id=current_user.id, rsvp_status='accepted')
        db.session.add(creator_att)

        db.session.commit()
        flash('Event created successfully!', 'success')
        return redirect(url_for('calendar.event_detail', event_id=event.id))

    # Pre-fill date from query param
    default_date = request.args.get('date', '')
    default_dt = ''
    if default_date:
        try:
            d = datetime.strptime(default_date, '%Y-%m-%d')
            default_dt = d.strftime('%Y-%m-%dT09:00')
        except ValueError:
            pass

    return render_template('calendar/create.html',
                           event_types=EVENT_TYPES,
                           reminder_options=REMINDER_OPTIONS,
                           projects=projects,
                           firm_users=firm_users,
                           default_dt=default_dt)


@calendar_bp.route('/<int:event_id>')
@simple_login_required
def event_detail(event_id):
    event = CalendarEvent.query.get_or_404(event_id)
    _check_access(event)
    can_edit = (event.created_by_id == current_user.id or
                current_user.is_admin() or current_user.is_super_admin())
    return render_template('calendar/detail.html', event=event, can_edit=can_edit)


@calendar_bp.route('/<int:event_id>/edit', methods=['GET', 'POST'])
@simple_login_required
def edit_event(event_id):
    event = CalendarEvent.query.get_or_404(event_id)
    _check_access(event)
    if not (event.created_by_id == current_user.id or
            current_user.is_admin() or current_user.is_super_admin()):
        abort(403)

    projects = get_firm_projects()
    firm_users = get_firm_users()
    current_attendee_ids = [a.user_id for a in event.attendees]

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Title is required.', 'danger')
        else:
            start_str = request.form.get('start_datetime', '')
            end_str = request.form.get('end_datetime', '')

            try:
                event.start_datetime = datetime.strptime(start_str, '%Y-%m-%dT%H:%M')
            except (ValueError, TypeError):
                flash('Invalid start date/time.', 'danger')
                return render_template('calendar/edit.html', event=event,
                                       event_types=EVENT_TYPES, event_statuses=EVENT_STATUSES,
                                       reminder_options=REMINDER_OPTIONS,
                                       projects=projects, firm_users=firm_users,
                                       current_attendee_ids=current_attendee_ids)

            event.title = title
            event.description = request.form.get('description', '').strip()
            event.event_type = request.form.get('event_type', event.event_type)
            event.status = request.form.get('status', event.status)
            event.end_datetime = None
            if end_str:
                try:
                    event.end_datetime = datetime.strptime(end_str, '%Y-%m-%dT%H:%M')
                except (ValueError, TypeError):
                    pass
            event.all_day = 'all_day' in request.form
            event.location = request.form.get('location', '').strip()
            event.virtual_link = request.form.get('virtual_link', '').strip()
            event.notes = request.form.get('notes', '').strip()

            proj_id = request.form.get('project_id', '')
            event.project_id = int(proj_id) if proj_id else None

            try:
                event.reminder_minutes = int(request.form.get('reminder_minutes', 60))
            except ValueError:
                event.reminder_minutes = 60

            # Update attendees
            CalendarEventAttendee.query.filter_by(event_id=event.id).delete()
            attendee_ids = request.form.getlist('attendee_ids')
            added = set()
            for uid in attendee_ids:
                if uid not in added:
                    att = CalendarEventAttendee(event_id=event.id, user_id=uid)
                    db.session.add(att)
                    added.add(uid)
            if current_user.id not in added:
                db.session.add(CalendarEventAttendee(event_id=event.id,
                                                     user_id=current_user.id,
                                                     rsvp_status='accepted'))

            db.session.commit()
            flash('Event updated.', 'success')
            return redirect(url_for('calendar.event_detail', event_id=event.id))

    return render_template('calendar/edit.html', event=event,
                           event_types=EVENT_TYPES, event_statuses=EVENT_STATUSES,
                           reminder_options=REMINDER_OPTIONS,
                           projects=projects, firm_users=firm_users,
                           current_attendee_ids=current_attendee_ids)


@calendar_bp.route('/<int:event_id>/delete', methods=['POST'])
@simple_login_required
def delete_event(event_id):
    event = CalendarEvent.query.get_or_404(event_id)
    _check_access(event)
    if not (event.created_by_id == current_user.id or
            current_user.is_admin() or current_user.is_super_admin()):
        abort(403)
    db.session.delete(event)
    db.session.commit()
    flash('Event deleted.', 'success')
    return redirect(url_for('calendar.index'))


@calendar_bp.route('/<int:event_id>/status', methods=['POST'])
@simple_login_required
def update_status(event_id):
    event = CalendarEvent.query.get_or_404(event_id)
    _check_access(event)
    new_status = request.form.get('status')
    if new_status in (EVENT_STATUS_UPCOMING, EVENT_STATUS_COMPLETED, EVENT_STATUS_CANCELLED):
        event.status = new_status
        db.session.commit()
        flash('Status updated.', 'success')
    return redirect(url_for('calendar.event_detail', event_id=event_id))


@calendar_bp.route('/upcoming')
@simple_login_required
def upcoming_events():
    events = (get_firm_events_query()
              .filter(CalendarEvent.start_datetime >= datetime.now(),
                      CalendarEvent.status == EVENT_STATUS_UPCOMING)
              .order_by(CalendarEvent.start_datetime)
              .all())
    return render_template('calendar/upcoming.html', events=events)


def _check_access(event):
    if current_user.is_super_admin():
        return
    if event.law_firm_id != current_user.law_firm_id:
        abort(403)
    if current_user.is_client():
        ids = [a.user_id for a in event.attendees]
        if current_user.id not in ids:
            abort(403)
