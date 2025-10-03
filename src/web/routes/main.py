"""
Main web routes for serving HTML pages.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from werkzeug.exceptions import NotFound

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def dashboard():
    """Main dashboard page."""
    return render_template('dashboard.html')


@main_bp.route('/streams')
def streams():
    """Stream configuration management page."""
    return render_template('streams.html')


@main_bp.route('/streams/new')
def new_stream():
    """Create new stream configuration page."""
    return render_template('stream_form.html', mode='create')


@main_bp.route('/streams/<int:stream_id>/edit')
def edit_stream(stream_id):
    """Edit existing stream configuration page."""
    return render_template('stream_form.html', mode='edit', stream_id=stream_id)


@main_bp.route('/schedules')
def schedules():
    """Recording schedule management page."""
    return render_template('schedules.html')


@main_bp.route('/schedules/new')
def new_schedule():
    """Create new recording schedule page."""
    return render_template('schedule_form.html', mode='create')


@main_bp.route('/schedules/<int:schedule_id>/edit')
def edit_schedule(schedule_id):
    """Edit existing recording schedule page."""
    return render_template('schedule_form.html', mode='edit', schedule_id=schedule_id)


@main_bp.route('/sessions')
def sessions():
    """Recording sessions monitoring page."""
    return render_template('sessions.html')


@main_bp.route('/logs')
def logs():
    """System logs viewing page."""
    return render_template('logs.html')


@main_bp.route('/settings')
def settings():
    """System settings and configuration page."""
    return render_template('settings.html')


@main_bp.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return render_template('error.html', 
                         error={'name': 'Page Not Found', 
                               'description': 'The requested page could not be found.'}), 404
@main
_bp.route('/backup')
def backup():
    """Configuration backup and restore page."""
    return render_template('backup.html')