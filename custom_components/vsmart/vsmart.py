"""VSmart API."""
from dataclasses import dataclass
from enum import Enum, auto
from logging import getLogger
from time import time
from typing import Any

from aiohttp import ClientResponse, ClientSession
import async_timeout

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_PASSWORD,
    CONF_USER_TOKEN,
    CONF_USER_TOKEN_EXPIRY,
    CONF_USERNAME,
)

_LOGGER = getLogger(__name__)
_HEADERS = {
    "Content-type": "application/json; charset=UTF-8",
    "X-Gizwits-Application-Id": "9109fb3ea6c04cf1be34c71ff82a51ec",
}
_TIMEOUT = 10

# How old the latest update can be before a spa is considered offline
_CONNECTIVITY_TIMEOUT = 1000


class TemperatureUnit(Enum):
    """Temperature units supported by the spa."""

    CELSIUS = auto()
    FAHRENHEIT = auto()


@dataclass
class VSmartDevice:
    """A device under a user's account."""

    device_id: str
    alias: str
    product_name: str


@dataclass
class VSmartDeviceStatus:
    """A snapshot of the status of a device."""

    timestamp: int
    heat_temp_now: float
    heat_temp_set: float
    temp_set_unit: TemperatureUnit
    heat_power: bool
    dhw_temp_now: float
    dhw_temp_set: float
    dhw_power: bool
    flow_temp: float
    rf_status: int

    @property
    def online(self) -> bool:
        """Determine whether the device is online based on the age of the latest update."""
        return self.rf_status == 3


@dataclass
class VSmartUserToken:
    """User authentication token, obtained (and ideally stored) following a successful login."""

    user_id: str
    user_token: str
    expiry: int


@dataclass
class VSmartDeviceReport:
    """A device report, which combines device metadata with a current status snapshot."""

    device: VSmartDevice
    status: VSmartDeviceStatus


class VSmartException(Exception):
    """An exception returned via the API."""


class VSmartOfflineException(VSmartException):
    """Device is offline."""

    def __init__(self) -> None:
        """Construct the exception."""
        super().__init__("Device is offline")


class VSmartAuthException(VSmartException):
    """An authentication error."""


class VSmartUserDoesNotExistException(VSmartAuthException):
    """User does not exist."""


class VSmartIncorrectPasswordException(VSmartAuthException):
    """Password is incorrect."""


async def raise_for_status(response: ClientResponse) -> None:
    """Raise an exception based on the response."""
    if response.ok:
        return

    # Try to parse out the vsmart error code
    try:
        api_error = await response.json()
    except Exception:  # pylint: disable=broad-except
        response.raise_for_status()

    error_code = api_error.get("error_code", 0)
    if error_code == 9004:
        raise VSmartAuthException()
    if error_code == 9005:
        raise VSmartUserDoesNotExistException()
    if error_code == 9042:
        raise VSmartOfflineException()
    if error_code == 9020:
        raise VSmartIncorrectPasswordException()

    # If we don't understand the error code, provide more detail for debugging
    response.raise_for_status()


class VSmartApi:
    """VSmart API."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, session: ClientSession, user_token: str, api_root: str) -> None:
        """Initialize the API with a user token."""
        self._hass = hass
        self._config_entry = entry
        self._session = session
        self._user_token = user_token
        self._api_root = api_root

        # Maps device IDs to device info
        self._bindings: dict[str, VSmartDevice] | None = None

        # Cache containing state information for each device received from the API
        # This is used to work around an annoyance where changes to settings via
        # a POST request are not immediately reflected in a subsequent GET request.
        #
        # When updating state via HA, we update the cache and return this value
        # until the API can provide us with a response containing a timestamp
        # more recent than the local update.
        self._local_state_cache: dict[str, VSmartDeviceStatus] = {}

    @staticmethod
    async def get_user_token(session: ClientSession, username: str, password: str, api_root: str) -> VSmartUserToken:
        """
        Login and obtain a user token.

        The server rate-limits requests for this fairly aggressively.
        """
        body = {"username": username, "password": password, "lang": "en"}

        async with async_timeout.timeout(_TIMEOUT):
            response = await session.post(
                f"{api_root}/app/login", headers=_HEADERS, json=body
            )
            await raise_for_status(response)
            api_data = await response.json()

        return VSmartUserToken(
            api_data["uid"], api_data["token"], api_data["expire_at"]
        )

    async def refresh_bindings(self) -> None:
        """Refresh and store the list of devices available in the account."""
        self._bindings = {
            device.device_id: device for device in await self._get_bindings()
        }

    async def _get_bindings(self) -> list[VSmartDevice]:
        """Get the list of devices available in the account."""
        headers = dict(_HEADERS)
        headers["X-Gizwits-User-token"] = self._user_token
        api_data = await self._do_get(f"{self._api_root}/app/bindings", headers)
        return list(
            map(
                lambda raw: VSmartDevice(
                    raw["did"], raw["dev_alias"], raw["product_name"]
                ),
                api_data["devices"],
            )
        )

    async def fetch_data(self) -> dict[str, VSmartDeviceReport]:
        """Fetch the latest data for all devices."""

        headers = dict(_HEADERS)
        headers["X-Gizwits-User-token"] = self._user_token

        results: dict[str, VSmartDeviceReport] = {}

        if not self._bindings:
            return results

        for did, device_info in self._bindings.items():
            latest_data = await self._do_get(
                f"{self._api_root}/app/devdata/{did}/latest", headers
            )

            # Work out whether the received API update is more recent than the
            # locally cached state
            api_update_timestamp = latest_data["updated_at"]
            local_update_timestamp = 0
            if cached_state := self._local_state_cache.get(did):
                local_update_timestamp = cached_state.timestamp

            # If the API timestamp is more recent, update the cache
            if api_update_timestamp >= local_update_timestamp:
                _LOGGER.debug("New data received for device %s", did)
                device_attrs = latest_data["attr"]

                errors = []
                #for err_num in range(1, 10):
                #    if device_attrs[f"system_err{err_num}"] == 1:
                #        errors.append(err_num)

                device_status = VSmartDeviceStatus(
                    latest_data["updated_at"],
                    device_attrs["Room_Temperature"],
                    device_attrs["Room_Temperature_Setpoint_Comfort"],
                    TemperatureUnit.CELSIUS,
                    device_attrs["Enabled_Heating"] == 1,
                    device_attrs["Tank_temperature"],
                    device_attrs["Current_DHW_Setpoint"],
                    device_attrs["Enabled_DHW"] == 1,
                    device_attrs["Flow_temperature"], 
                    device_attrs["RF_Status"],                  
                )

                self._local_state_cache[did] = device_status

            else:
                _LOGGER.debug(
                    "Ignoring update for device %s as local data is newer", did
                )

            results[did] = VSmartDeviceReport(
                device_info,
                self._local_state_cache[did],
            )

        return results

    async def set_heat(self, device_id: str, heat: bool) -> None:
        """
        Turn the heater on/off.

        Turning the heater on will also turn on the filter pump.
        """
        _LOGGER.debug("Setting heater mode to %s", "ON" if heat else "OFF")
        headers = dict(_HEADERS)
        headers["X-Gizwits-User-token"] = self._user_token
        await self._do_post(
            f"{self._api_root}/app/control/{device_id}",
            headers,
            {"attrs": {"Heating_Enable": 1 if heat else 0}},
        )
        self._local_state_cache[device_id].timestamp = int(time())
        self._local_state_cache[device_id].heat_power = heat

    async def set_dhw(self, device_id: str, heat: bool) -> None:
        """
        Turn the DHW on/off.

        Turning the DHW on will also turn on the filter pump.
        """
        _LOGGER.debug("Setting DHW mode to %s", "ON" if heat else "OFF")
        headers = dict(_HEADERS)
        headers["X-Gizwits-User-token"] = self._user_token
        await self._do_post(
            f"{self._api_root}/app/control/{device_id}",
            headers,
            {"attrs": {"WarmStar_Tank_Loading_Enable": 1 if heat else 0}},
        )
        self._local_state_cache[device_id].timestamp = int(time())
        self._local_state_cache[device_id].dhw_power = heat

    async def set_heat_temp(self, device_id: str, target_temp: int) -> None:
        """Set the target temperature."""
        _LOGGER.debug("Setting target temperature to %d", target_temp)
        headers = dict(_HEADERS)
        headers["X-Gizwits-User-token"] = self._user_token
        await self._do_post(
            f"{self._api_root}/app/control/{device_id}",
            headers,
            {"attrs": {"Room_Temperature_Setpoint_Comfort": target_temp}},
        )
        self._local_state_cache[device_id].timestamp = int(time())
        self._local_state_cache[device_id].heat_temp_set = target_temp

    async def set_dhw_temp(self, device_id: str, target_temp: int) -> None:
        """Set the target temperature."""
        _LOGGER.debug("Setting DHW temperature to %d", target_temp)
        headers = dict(_HEADERS)
        headers["X-Gizwits-User-token"] = self._user_token
        await self._do_post(
            f"{self._api_root}/app/control/{device_id}",
            headers,
            {"attrs": {"DHW_setpoint": target_temp}},
        )
        self._local_state_cache[device_id].timestamp = int(time())
        self._local_state_cache[device_id].dhw_temp_set = target_temp

    async def _do_get(self, url: str, headers: dict[str, str]) -> dict[str, Any]:
        return await self._make_request("GET", url, headers)
    
    async def _do_post(self, url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        return await self._make_request("POST", url, headers, body)
    
    async def _make_request(self, method: str, url: str, headers: dict[str, str], body: dict[str, Any] = None) -> dict[str, Any]:
        """Make an API call to the specified URL, returning the response as a JSON object."""
        async with async_timeout.timeout(_TIMEOUT):
            if method == "POST":
                response = await self._session.post(url, headers=headers, json=body)
            else:
                response = await self._session.get(url, headers=headers)

            _LOGGER.debug(f"METHOD={method},URL={url}, HEADER={headers}, BODY={body}")

            try:
                await raise_for_status(response)
                # 记录响应状态码和内容
                response_data = await response.json(content_type=None)
                _LOGGER.debug(f"RESPONSE STATUS={response.status}, RESPONSE BODY={response_data}")
                return response_data

            except VSmartAuthException:
                _LOGGER.warning("VSmartAuthException encountered, attempting to refresh token.")
                try:
                    # 更新 token
                    token = await self.get_user_token(self._session, self._config_entry.data.get(CONF_USERNAME), self._config_entry.data.get(CONF_PASSWORD), self._api_root)
                    user_token = token.user_token
                    user_token_expiry = token.expiry

                    new_config_data = {
                        CONF_USER_TOKEN: user_token,
                        CONF_USER_TOKEN_EXPIRY: user_token_expiry,
                    }

                    self._hass.config_entries.async_update_entry(
                        self._config_entry, data={**self._config_entry.data, **new_config_data}
                    )

                    self._user_token = user_token

                    return await self._make_request(method, url, headers, body)
                except Exception as ex:
                    raise ConfigEntryNotReady from ex
