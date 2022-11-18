"""Config flow for VSmart integration."""
from __future__ import annotations

from logging import getLogger
from typing import Any

from aiohttp import ClientConnectionError
import async_timeout
from homeassistant.config_entries import ConfigFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

from custom_components.vsmart.vsmart import (
    VSmartIncorrectPasswordException,
    VSmartUserDoesNotExistException,
)

from .vsmart import VSmartApi
from .const import (
    CONF_API_ROOT,
    CONF_API_ROOT_CN,
    CONF_API_ROOT_EU,
    CONF_API_ROOT_US,
    CONF_PASSWORD,
    CONF_USER_TOKEN,
    CONF_USER_TOKEN_EXPIRY,
    CONF_USERNAME,
    DOMAIN,
)

_LOGGER = getLogger(__name__)
_STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_API_ROOT): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(value=CONF_API_ROOT_CN, label="CN"),
                    selector.SelectOptionDict(value=CONF_API_ROOT_EU, label="EU"),
                    selector.SelectOptionDict(value=CONF_API_ROOT_US, label="US"),
                ]
            )
        ),
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    username = data[CONF_USERNAME]
    api_root = data[CONF_API_ROOT]
    session = async_get_clientsession(hass)
    async with async_timeout.timeout(10):
        token = await VSmartApi.get_user_token(
            session, username, data[CONF_PASSWORD], api_root
        )

    return {
        "title": username,
        CONF_API_ROOT: api_root,
        CONF_USER_TOKEN: token.user_token,
        CONF_USER_TOKEN_EXPIRY: token.expiry,
    }


class VSmartConfigFlow(ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Handle a config flow for vsmart."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=_STEP_USER_DATA_SCHEMA
            )

        errors = {}

        try:
            info = await validate_input(self.hass, user_input)
        except VSmartUserDoesNotExistException:
            errors["base"] = "user_does_not_exist"
        except VSmartIncorrectPasswordException:
            errors["base"] = "incorrect_password"
        except ClientConnectionError:
            errors["base"] = "cannot_connect"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown_connection_error"
        else:
            return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=_STEP_USER_DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""
