-- Disposable contract checks. All inserted rows are rolled back.
begin;

insert into public.requests (request_type, conversation_id, location, callback_phone, noise_source)
values ('noise_complaint', 'contract-check-noise', 'Test address', '(555) 010-0000', 'Loud music');

insert into public.requests (request_type, conversation_id, location, callback_phone, vehicle_description, license_plate, blocking_driveway)
values ('illegally_parked_vehicle', 'contract-check-vehicle', 'Test address', '(555) 010-0000', 'White van', null, false);

insert into public.requests (request_type, conversation_id, location, callback_phone, pothole_size, hazard_to_traffic)
values ('pothole', 'contract-check-pothole', 'Test intersection', '(555) 010-0000', 'One foot wide', false);

insert into public.handoffs (conversation_id, transcript, trigger_label)
values ('contract-check-handoff', 'Turn 1: Resident reports a fire.', 'fire');

do $$
begin
    begin
        insert into public.requests (request_type, conversation_id, location, callback_phone)
        values ('noise_complaint', 'contract-check-missing-source', 'Test address', '(555) 010-0000');
        raise exception 'FAIL: missing noise_source was accepted';
    exception when check_violation then null;
    end;
    begin
        insert into public.requests (request_type, conversation_id, location, callback_phone, pothole_size)
        values ('pothole', 'contract-check-missing-boolean', 'Test address', '(555) 010-0000', 'Small');
        raise exception 'FAIL: missing hazard_to_traffic was accepted';
    exception when check_violation then null;
    end;
    begin
        insert into public.requests (request_type, conversation_id, location, callback_phone, noise_source, vehicle_description)
        values ('noise_complaint', 'contract-check-extra', 'Test address', '(555) 010-0000', 'Music', 'Unexpected van');
        raise exception 'FAIL: cross-type field was accepted';
    exception when check_violation then null;
    end;
    begin
        insert into public.handoffs (conversation_id, transcript, trigger_label)
        values ('contract-check-bad-trigger', 'Resident message', '');
        raise exception 'FAIL: blank trigger was accepted';
    exception when check_violation then null;
    end;
end;
$$;

-- Verify actual trigger execution, including unchanged rows and creation timestamps.
do $$
declare
    previous_updated_at timestamptz;
    previous_created_at timestamptz;
    changed_updated_at timestamptz;
    changed_created_at timestamptz;
    unchanged_updated_at timestamptz;
begin
    select updated_at, created_at into strict previous_updated_at, previous_created_at
    from public.requests where conversation_id = 'contract-check-noise';

    update public.requests set noise_source = 'Updated loud music'
    where conversation_id = 'contract-check-noise'
    returning updated_at, created_at into strict changed_updated_at, changed_created_at;

    if changed_updated_at <= previous_updated_at or changed_created_at <> previous_created_at then
        raise exception 'FAIL: requests trigger must advance updated_at and preserve created_at';
    end if;

    update public.requests set noise_source = noise_source
    where conversation_id = 'contract-check-noise'
    returning updated_at into strict unchanged_updated_at;

    if unchanged_updated_at <> changed_updated_at then
        raise exception 'FAIL: requests no-op UPDATE changed updated_at';
    end if;

    select updated_at, created_at into strict previous_updated_at, previous_created_at
    from public.handoffs where conversation_id = 'contract-check-handoff';

    update public.handoffs set transcript = 'Turn 1: Resident reports smoke and a fire.'
    where conversation_id = 'contract-check-handoff'
    returning updated_at, created_at into strict changed_updated_at, changed_created_at;

    if changed_updated_at <= previous_updated_at or changed_created_at <> previous_created_at then
        raise exception 'FAIL: handoffs trigger must advance updated_at and preserve created_at';
    end if;

    update public.handoffs set transcript = transcript
    where conversation_id = 'contract-check-handoff'
    returning updated_at into strict unchanged_updated_at;

    if unchanged_updated_at <> changed_updated_at then
        raise exception 'FAIL: handoffs no-op UPDATE changed updated_at';
    end if;
end;
$$;

select 'PASS: three request shapes, nullable plate, false booleans, handoff, four rejection cases, and both row-update triggers (changed and unchanged rows)' as result;
rollback;
