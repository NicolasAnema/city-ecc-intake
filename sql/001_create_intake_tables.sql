-- City ECC typed intake contract. Apply once to a fresh Supabase public schema.
begin;

create table public.requests (
    id bigint generated always as identity primary key,
    request_type text not null check (request_type in (
        'noise_complaint', 'illegally_parked_vehicle', 'pothole'
    )),
    conversation_id text not null unique check (length(btrim(conversation_id)) > 0),
    location text not null check (length(btrim(location)) > 0),
    callback_phone text not null check (length(btrim(callback_phone)) > 0),
    noise_source text check (noise_source is null or length(btrim(noise_source)) > 0),
    vehicle_description text check (vehicle_description is null or length(btrim(vehicle_description)) > 0),
    license_plate text check (license_plate is null or length(btrim(license_plate)) > 0),
    blocking_driveway boolean,
    pothole_size text check (pothole_size is null or length(btrim(pothole_size)) > 0),
    hazard_to_traffic boolean,
    created_at timestamptz not null default now(),
    -- Fields for other types are NULL. Each type's required fields remain enforced.
    constraint requests_type_shape check (
        (request_type = 'noise_complaint'
            and noise_source is not null
            and vehicle_description is null and license_plate is null and blocking_driveway is null
            and pothole_size is null and hazard_to_traffic is null)
        or (request_type = 'illegally_parked_vehicle'
            and vehicle_description is not null and blocking_driveway is not null
            and noise_source is null and pothole_size is null and hazard_to_traffic is null)
        or (request_type = 'pothole'
            and pothole_size is not null and hazard_to_traffic is not null
            and noise_source is null and vehicle_description is null
            and license_plate is null and blocking_driveway is null)
    )
);

comment on column public.requests.license_plate is
    'Nullable for routine samples ECC-T-010, ECC-T-025, ECC-T-037: resident cannot read the plate.';

create table public.handoffs (
    id bigint generated always as identity primary key,
    conversation_id text not null unique check (length(btrim(conversation_id)) > 0),
    transcript text not null check (length(btrim(transcript)) > 0),
    trigger_label text not null check (trigger_label in (
        'weapon', 'injury', 'fire', 'danger', 'person_in_distress', 'unclassified_after_two_tries'
    )),
    created_at timestamptz not null default now()
);

-- No public API access policy yet; future agent/service authorization is outside this contract.
alter table public.requests enable row level security;
alter table public.handoffs enable row level security;

commit;
