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

select 'PASS: three request shapes, nullable plate, false booleans, handoff, and four rejection cases' as result;
rollback;
