from flask import abort, redirect, render_template, session

from app import current_service, current_user, url_for
from app.main import main
from app.main.views.send import (
    all_placeholders_in_session,
    fields_to_fill_in,
    get_normalised_placeholders_from_session,
    get_notification_check_endpoint,
    get_placeholder_form_instance,
    get_recipient_and_placeholders_from_session,
)
from app.utils import get_template, user_has_permissions


@main.route("/services/<uuid:service_id>/tour/<uuid:template_id>")
@user_has_permissions('send_messages')
def begin_tour(service_id, template_id):
    db_template = current_service.get_template(template_id)

    if (db_template['template_type'] != 'sms' or not current_user.mobile_number):
        abort(404)

    template = get_template(
        db_template,
        current_service,
        show_recipient=True,
    )

    template.values = {"phone_number": current_user.mobile_number}

    session['placeholders'] = {}

    return render_template(
        'views/templates/start-tour.html',
        template=template,
        help='1',
        continue_link=url_for('.tour_step', service_id=service_id, template_id=template_id, step_index=1)
    )


@main.route(
    "/services/<uuid:service_id>/tour/<uuid:template_id>/step-<int:step_index>",
    methods=['GET', 'POST'],
)
@user_has_permissions('send_messages', restrict_admin_usage=True)
def tour_step(service_id, template_id, step_index):
    db_template = current_service.get_template(template_id)

    if db_template['template_type'] != 'sms':
        abort(404)

    template = get_template(
        db_template,
        current_service,
        show_recipient=True,
    )

    placeholders = fields_to_fill_in(template, prefill_current_user=True)
    try:
        # user urls are 1 indexed, so start at step-1
        current_placeholder = placeholders[step_index - 1]
    except IndexError:
        if all_placeholders_in_session(placeholders):
            return get_notification_check_endpoint(service_id, template)
        return redirect(url_for(
            '.tour_step', service_id=current_service.id, template_id=db_template['id'], step_index=1
        ))

    form = get_placeholder_form_instance(
        current_placeholder,
        dict_to_populate_from=get_normalised_placeholders_from_session(),
        template_type=template.template_type,
        allow_international_phone_numbers=current_service.has_permission('international_sms')
    )

    if form.validate_on_submit():
        session['placeholders'][current_placeholder] = form.placeholder_value.data

        if all_placeholders_in_session(placeholders):
            return get_notification_check_endpoint(service_id, template)
        return redirect(url_for(
            '.tour_step', service_id=current_service.id, template_id=db_template['id'], step_index=step_index + 1
        ))

    back_link = _get_tour_step_back_link(service_id, template_id, step_index)

    template.values = get_recipient_and_placeholders_from_session(db_template['template_type'])
    template.values[current_placeholder] = None

    return render_template(
        'views/send-test.html',
        page_title="Example text message",
        template=template,
        form=form,
        back_link=back_link,
        help='2'
    )


def _get_tour_step_back_link(service_id, template_id, step_index):
    if step_index == 1:
        return url_for('.begin_tour', service_id=service_id, template_id=template_id)

    return url_for('.tour_step', service_id=service_id, template_id=template_id, step_index=step_index - 1)
