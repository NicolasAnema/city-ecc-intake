"""Three distinct dispatch contracts derived from the labeled routine chats."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class NoiseComplaint(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    request_type: Literal["noise_complaint"]
    conversation_id: NonBlankText
    location: NonBlankText
    noise_source: NonBlankText
    callback_phone: NonBlankText


class IllegallyParkedVehicle(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    request_type: Literal["illegally_parked_vehicle"]
    conversation_id: NonBlankText
    location: NonBlankText
    vehicle_description: NonBlankText
    # ECC-T-010, ECC-T-025, ECC-T-037 have unreadable plates: required key, nullable value.
    license_plate: NonBlankText | None
    blocking_driveway: bool
    callback_phone: NonBlankText


class Pothole(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    request_type: Literal["pothole"]
    conversation_id: NonBlankText
    location: NonBlankText
    pothole_size: NonBlankText
    hazard_to_traffic: bool
    callback_phone: NonBlankText


MODEL_BY_TYPE: dict[str, type[NoiseComplaint] | type[IllegallyParkedVehicle] | type[Pothole]] = {
    "noise_complaint": NoiseComplaint,
    "illegally_parked_vehicle": IllegallyParkedVehicle,
    "pothole": Pothole,
}
