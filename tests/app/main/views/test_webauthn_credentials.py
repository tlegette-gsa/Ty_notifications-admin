import base64

import pytest
from fido2 import cbor
from flask import url_for

from app.models.webauthn_credential import RegistrationError, WebAuthnCredential


@pytest.fixture
def webauthn_authentication_post_data(fake_uuid, webauthn_credential, client):
    """
    Sets up session, challenge, etc as if a user with uuid `fake_uuid` has logged in and touched the webauthn token
    as found in the `webauthn_credential` fixture. Sets up the session as if `begin_authentication` had been called
    so that the challenge matches and the credential will validate (provided that the key belongs to the user referenced
    in the session).
    """
    with client.session_transaction() as session:
        session['user_details'] = {'id': fake_uuid}
        session['webauthn_authentication_state'] = {
            "challenge": "e-g-nXaRxMagEiqTJSyD82RsEc5if_6jyfJDy8bNKlw",
            "user_verification": None
        }

    credential_id = WebAuthnCredential(webauthn_credential).to_credential_data().credential_id

    return cbor.encode({
        'credentialId': credential_id,
        'authenticatorData': base64.b64decode(b'dKbqkhPJnC90siSSsyDPQCYqlMGpUKA5fyklC2CEHvABAAACfQ=='),
        'clientDataJSON': b'{"challenge":"e-g-nXaRxMagEiqTJSyD82RsEc5if_6jyfJDy8bNKlw","origin":"https://webauthn.io","type":"webauthn.get"}',  # noqa
        'signature': bytes.fromhex('304502204a76f05cd52a778cdd4df1565e0004e5cc1ead360419d0f5c3a0143bf37e7f15022100932b5c308a560cfe4f244214843075b904b3eda64e85d64662a81198c386cdde'),  # noqa
    })


@pytest.mark.parametrize('endpoint', [
    'webauthn_begin_register',
])
def test_register_forbidden_for_non_platform_admins(
    client_request,
    endpoint,
):
    client_request.get(f'main.{endpoint}', _expected_status=403)


def test_begin_register_returns_encoded_options(
    mocker,
    platform_admin_user,
    platform_admin_client,
    webauthn_dev_server,
):
    mocker.patch('app.user_api_client.get_webauthn_credentials_for_user', return_value=[])
    response = platform_admin_client.get(url_for('main.webauthn_begin_register'))

    assert response.status_code == 200

    webauthn_options = cbor.decode(response.data)['publicKey']
    assert webauthn_options['attestation'] == 'direct'
    assert webauthn_options['timeout'] == 30_000

    auth_selection = webauthn_options['authenticatorSelection']
    assert auth_selection['authenticatorAttachment'] == 'cross-platform'
    assert auth_selection['userVerification'] == 'discouraged'

    user_options = webauthn_options['user']
    assert user_options['name'] == platform_admin_user['email_address']
    assert user_options['id'] == bytes(platform_admin_user['id'], 'utf-8')

    relying_party_options = webauthn_options['rp']
    assert relying_party_options['name'] == 'GOV.UK Notify'
    assert relying_party_options['id'] == 'webauthn.io'


def test_begin_register_includes_existing_credentials(
    platform_admin_client,
    webauthn_credential,
    mocker,
):
    mocker.patch(
        'app.user_api_client.get_webauthn_credentials_for_user',
        return_value=[webauthn_credential, webauthn_credential]
    )

    response = platform_admin_client.get(
        url_for('main.webauthn_begin_register')
    )

    webauthn_options = cbor.decode(response.data)['publicKey']
    assert len(webauthn_options['excludeCredentials']) == 2


def test_begin_register_stores_state_in_session(
    platform_admin_client,
    mocker,
):
    mocker.patch(
        'app.user_api_client.get_webauthn_credentials_for_user',
        return_value=[])

    response = platform_admin_client.get(
        url_for('main.webauthn_begin_register')
    )

    assert response.status_code == 200

    with platform_admin_client.session_transaction() as session:
        assert session['webauthn_registration_state'] is not None


def test_complete_register_creates_credential(
    platform_admin_user,
    platform_admin_client,
    mocker,
):
    with platform_admin_client.session_transaction() as session:
        session['webauthn_registration_state'] = 'state'

    user_api_mock = mocker.patch(
        'app.user_api_client.create_webauthn_credential_for_user'
    )

    credential_mock = mocker.patch(
        'app.models.webauthn_credential.WebAuthnCredential.from_registration',
        return_value='cred'
    )

    response = platform_admin_client.post(
        url_for('main.webauthn_complete_register'),
        data=cbor.encode('public_key_credential'),
    )

    assert response.status_code == 200
    credential_mock.assert_called_once_with('state', 'public_key_credential')
    user_api_mock.assert_called_once_with(platform_admin_user['id'], 'cred')


def test_complete_register_clears_session(
    platform_admin_client,
    mocker,
):
    with platform_admin_client.session_transaction() as session:
        session['webauthn_registration_state'] = 'state'

    mocker.patch('app.user_api_client.create_webauthn_credential_for_user')
    mocker.patch('app.models.webauthn_credential.WebAuthnCredential.from_registration')

    platform_admin_client.post(
        url_for('main.webauthn_complete_register'),
        data=cbor.encode('public_key_credential'),
    )

    with platform_admin_client.session_transaction() as session:
        assert 'webauthn_registration_state' not in session


def test_complete_register_handles_library_errors(
    platform_admin_client,
    mocker,
):
    with platform_admin_client.session_transaction() as session:
        session['webauthn_registration_state'] = 'state'

    mocker.patch(
        'app.models.webauthn_credential.WebAuthnCredential.from_registration',
        side_effect=RegistrationError('error')
    )

    response = platform_admin_client.post(
        url_for('main.webauthn_complete_register'),
        data=cbor.encode('public_key_credential'),
    )

    assert response.status_code == 400
    assert cbor.decode(response.data) == 'error'


def test_complete_register_handles_missing_state(
    platform_admin_client,
    mocker,
):
    response = platform_admin_client.post(
        url_for('main.webauthn_complete_register'),
        data=cbor.encode('public_key_credential'),
    )

    assert response.status_code == 400
    assert cbor.decode(response.data) == 'No registration in progress'


def test_begin_authentication_forbidden_for_non_platform_admins(client, api_user_active, mock_get_user):
    # mock_get_user returns api_user_active so changes to the api user will reflect
    api_user_active['auth_type'] = 'webauthn_auth'

    with client.session_transaction() as session:
        session['user_details'] = {'id': '1'}

    response = client.get(url_for('main.webauthn_begin_authentication'))
    assert response.status_code == 403


def test_begin_authentication_forbidden_for_users_without_webauthn(client, mocker, platform_admin_user):
    mocker.patch('app.user_api_client.get_user', return_value=platform_admin_user)

    with client.session_transaction() as session:
        session['user_details'] = {'id': '1'}

    response = client.get(url_for('main.webauthn_begin_authentication'))
    assert response.status_code == 403


def test_begin_authentication_returns_encoded_options(client, mocker, webauthn_credential, platform_admin_user):
    platform_admin_user['auth_type'] = 'webauthn_auth'
    mocker.patch('app.user_api_client.get_user', return_value=platform_admin_user)

    with client.session_transaction() as session:
        session['user_details'] = {'id': platform_admin_user['id']}

    get_creds_mock = mocker.patch(
        'app.user_api_client.get_webauthn_credentials_for_user',
        return_value=[webauthn_credential]
    )
    response = client.get(url_for('main.webauthn_begin_authentication'))

    decoded_data = cbor.decode(response.data)
    allowed_credentials = decoded_data['publicKey']['allowCredentials']

    assert len(allowed_credentials) == 1
    assert decoded_data['publicKey']['timeout'] == 30000
    get_creds_mock.assert_called_once_with(platform_admin_user['id'])


def test_begin_authentication_stores_state_in_session(client, mocker, webauthn_credential, platform_admin_user):
    platform_admin_user['auth_type'] = 'webauthn_auth'
    mocker.patch('app.user_api_client.get_user', return_value=platform_admin_user)

    with client.session_transaction() as session:
        session['user_details'] = {'id': platform_admin_user['id']}

    mocker.patch(
        'app.user_api_client.get_webauthn_credentials_for_user',
        return_value=[webauthn_credential]
    )
    client.get(url_for('main.webauthn_begin_authentication'))

    with client.session_transaction() as session:
        assert 'challenge' in session['webauthn_authentication_state']


def test_complete_authentication_checks_credentials(
    client,
    mocker,
    webauthn_credential,
    webauthn_dev_server,
    mock_create_event,
    webauthn_authentication_post_data,
    platform_admin_user
):
    platform_admin_user['auth_type'] = 'webauthn_auth'
    mocker.patch('app.user_api_client.get_user', return_value=platform_admin_user)
    mocker.patch('app.user_api_client.get_webauthn_credentials_for_user', return_value=[webauthn_credential])

    response = client.post(url_for('main.webauthn_complete_authentication'), data=webauthn_authentication_post_data)
    assert response.status_code == 302


def test_complete_authentication_403s_if_key_isnt_in_users_credentials(
    client,
    mocker,
    webauthn_credential,
    webauthn_dev_server,
    webauthn_authentication_post_data,
    platform_admin_user
):
    platform_admin_user['auth_type'] = 'webauthn_auth'
    mocker.patch('app.user_api_client.get_user', return_value=platform_admin_user)
    # user has no keys in the database
    mocker.patch('app.user_api_client.get_webauthn_credentials_for_user', return_value=[])

    response = client.post(url_for('main.webauthn_complete_authentication'), data=webauthn_authentication_post_data)
    assert response.status_code == 403

    with client.session_transaction() as session:
        assert session['user_details']['id'] == platform_admin_user['id']
        # user not logged in
        assert 'user_id' not in session
        # webauthn state reset so can't replay
        assert 'webauthn_authentication_state' not in session


def test_complete_authentication_clears_session(
    client,
    mocker,
    webauthn_credential,
    webauthn_dev_server,
    webauthn_authentication_post_data,
    mock_create_event,
    platform_admin_user
):
    platform_admin_user['auth_type'] = 'webauthn_auth'
    mocker.patch('app.user_api_client.get_user', return_value=platform_admin_user)
    mocker.patch('app.user_api_client.get_webauthn_credentials_for_user', return_value=[webauthn_credential])

    response = client.post(url_for('main.webauthn_complete_authentication'), data=webauthn_authentication_post_data)
    assert response.status_code == 302

    with client.session_transaction() as session:
        # it's important that we clear the session to ensure that we don't re-use old login artifacts in future
        assert 'webauthn_authentication_state' not in session
