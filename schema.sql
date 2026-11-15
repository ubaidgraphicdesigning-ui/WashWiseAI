-- WashWise AI — fresh real-business database schema
-- Apply this entire file once in Supabase SQL Editor.
-- This edition intentionally has NO public signup/login. The Streamlit server
-- uses a server-side Supabase secret key and a shared Staff PIN for write access.
-- Never expose the Supabase secret key in source control or browser code.

create extension if not exists pgcrypto;

create table if not exists public.businesses (
    id uuid primary key default gen_random_uuid(),
    business_name text not null,
    phone text not null,
    email text,
    address text not null,
    currency text not null default 'PKR',
    timezone text not null default 'Asia/Karachi',
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.customers (
    id uuid primary key default gen_random_uuid(),
    business_id uuid not null references public.businesses(id) on delete cascade,
    full_name text not null,
    phone text not null,
    email text,
    address text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists customers_business_phone_idx on public.customers(business_id, phone);

create table if not exists public.services (
    id uuid primary key default gen_random_uuid(),
    business_id uuid not null references public.businesses(id) on delete cascade,
    name text not null,
    unit text not null default 'piece',
    unit_price numeric(12,2) not null check (unit_price >= 0),
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    unique (business_id, name)
);

create table if not exists public.orders (
    id uuid primary key default gen_random_uuid(),
    business_id uuid not null references public.businesses(id) on delete cascade,
    order_no text not null,
    customer_id uuid not null references public.customers(id),
    status text not null default 'received' check (status in (
        'received','inspection','washing','ironing','ready','out_for_delivery','delivered','cancelled'
    )),
    notes text,
    received_at timestamptz not null default now(),
    due_at timestamptz,
    total numeric(12,2) not null default 0 check (total >= 0),
    paid numeric(12,2) not null default 0 check (paid >= 0),
    balance numeric(12,2) generated always as (total - paid) stored,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (business_id, order_no),
    check (paid <= total)
);
create index if not exists orders_business_status_idx on public.orders(business_id, status);
create index if not exists orders_business_created_idx on public.orders(business_id, created_at desc);
create index if not exists orders_business_due_idx on public.orders(business_id, due_at);

create table if not exists public.order_items (
    id uuid primary key default gen_random_uuid(),
    business_id uuid not null references public.businesses(id) on delete cascade,
    order_id uuid not null references public.orders(id) on delete cascade,
    service_id uuid references public.services(id) on delete set null,
    garment_name text not null,
    service_name text not null,
    quantity numeric(10,2) not null check (quantity > 0),
    unit_price numeric(12,2) not null check (unit_price >= 0),
    line_total numeric(12,2) generated always as (quantity * unit_price) stored,
    created_at timestamptz not null default now()
);
create index if not exists order_items_business_order_idx on public.order_items(business_id, order_id);

create table if not exists public.payments (
    id uuid primary key default gen_random_uuid(),
    business_id uuid not null references public.businesses(id) on delete cascade,
    order_id uuid not null references public.orders(id) on delete restrict,
    amount numeric(12,2) not null check (amount > 0),
    method text not null,
    reference text,
    received_at timestamptz not null default now()
);
create index if not exists payments_business_received_idx on public.payments(business_id, received_at desc);

create table if not exists public.order_status_history (
    id uuid primary key default gen_random_uuid(),
    business_id uuid not null references public.businesses(id) on delete cascade,
    order_id uuid not null references public.orders(id) on delete cascade,
    old_status text,
    new_status text not null,
    note text,
    changed_at timestamptz not null default now()
);

create table if not exists public.inventory_items (
    id uuid primary key default gen_random_uuid(),
    business_id uuid not null references public.businesses(id) on delete cascade,
    item_name text not null,
    unit text not null default 'piece',
    quantity_on_hand numeric(12,2) not null default 0 check (quantity_on_hand >= 0),
    reorder_level numeric(12,2) not null default 0 check (reorder_level >= 0),
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    unique (business_id, item_name)
);

create table if not exists public.inventory_movements (
    id uuid primary key default gen_random_uuid(),
    business_id uuid not null references public.businesses(id) on delete cascade,
    item_id uuid not null references public.inventory_items(id) on delete cascade,
    movement_type text not null,
    quantity_change numeric(12,2) not null,
    note text,
    created_at timestamptz not null default now()
);

create table if not exists public.expenses (
    id uuid primary key default gen_random_uuid(),
    business_id uuid not null references public.businesses(id) on delete cascade,
    category text not null,
    amount numeric(12,2) not null check (amount > 0),
    expense_date date not null default current_date,
    description text,
    created_at timestamptz not null default now()
);

create or replace function public.ww_create_order(
    p_business_id uuid,
    p_customer_name text,
    p_customer_phone text,
    p_customer_address text,
    p_due_at timestamptz,
    p_items jsonb,
    p_notes text default null
) returns jsonb
language plpgsql security definer set search_path = public
as $$
declare
    v_customer_id uuid;
    v_order_id uuid;
    v_order_no text;
    v_total numeric(12,2) := 0;
    v_item jsonb;
    v_qty numeric(10,2);
    v_price numeric(12,2);
    v_service_id uuid;
    v_service_name text;
    v_garment text;
begin
    if nullif(trim(p_customer_name), '') is null or nullif(trim(p_customer_phone), '') is null then
        raise exception 'Customer name and phone are required';
    end if;
    if p_items is null or jsonb_typeof(p_items) is distinct from 'array' or jsonb_array_length(p_items) = 0 then
        raise exception 'At least one order item is required';
    end if;

    select id into v_customer_id from public.customers
    where business_id = p_business_id and phone = trim(p_customer_phone) limit 1;

    if v_customer_id is null then
        insert into public.customers(business_id, full_name, phone, address)
        values (p_business_id, trim(p_customer_name), trim(p_customer_phone), nullif(trim(coalesce(p_customer_address,'')), ''))
        returning id into v_customer_id;
    else
        update public.customers set full_name = trim(p_customer_name),
            address = coalesce(nullif(trim(coalesce(p_customer_address,'')), ''), address),
            updated_at = now() where id = v_customer_id;
    end if;

    v_order_no := 'WW-' || to_char(now() at time zone 'Asia/Karachi', 'YYMMDD') || '-' || upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 6));
    insert into public.orders(business_id, order_no, customer_id, status, notes, due_at, total, paid)
    values (p_business_id, v_order_no, v_customer_id, 'received', p_notes, p_due_at, 0, 0)
    returning id into v_order_id;

    for v_item in select * from jsonb_array_elements(p_items) loop
        v_qty := (v_item->>'quantity')::numeric;
        v_price := (v_item->>'unit_price')::numeric;
        v_garment := trim(coalesce(v_item->>'garment_name',''));
        v_service_name := trim(coalesce(v_item->>'service_name',''));
        v_service_id := nullif(v_item->>'service_id','')::uuid;
        if v_qty is null or v_qty <= 0 or v_price is null or v_price < 0 or v_garment = '' or v_service_name = '' then
            raise exception 'Invalid order item';
        end if;
        if v_service_id is not null and not exists (
            select 1 from public.services where id = v_service_id and business_id = p_business_id and is_active = true
        ) then raise exception 'Selected service is not active for this business'; end if;
        insert into public.order_items(business_id, order_id, service_id, garment_name, service_name, quantity, unit_price)
        values (p_business_id, v_order_id, v_service_id, v_garment, v_service_name, v_qty, v_price);
        v_total := v_total + round(v_qty * v_price, 2);
    end loop;

    update public.orders set total = v_total, updated_at = now() where id = v_order_id;
    insert into public.order_status_history(business_id, order_id, old_status, new_status, note)
    values (p_business_id, v_order_id, null, 'received', 'Order created');
    return jsonb_build_object('id', v_order_id, 'order_no', v_order_no, 'total', v_total, 'customer_id', v_customer_id);
end;
$$;

create or replace function public.ww_record_payment(
    p_business_id uuid, p_order_id uuid, p_amount numeric, p_method text, p_reference text default null
) returns jsonb
language plpgsql security definer set search_path = public
as $$
declare v_order public.orders%rowtype; v_new_paid numeric(12,2);
begin
    if p_amount is null or p_amount <= 0 then raise exception 'Payment must be greater than zero'; end if;
    select * into v_order from public.orders where id = p_order_id and business_id = p_business_id for update;
    if not found then raise exception 'Order not found'; end if;
    v_new_paid := v_order.paid + p_amount;
    if v_new_paid > v_order.total then raise exception 'Payment exceeds the outstanding balance'; end if;
    insert into public.payments(business_id, order_id, amount, method, reference)
    values (p_business_id, p_order_id, p_amount, p_method, p_reference);
    update public.orders set paid = v_new_paid, updated_at = now() where id = p_order_id;
    return jsonb_build_object('order_id', p_order_id, 'paid', v_new_paid, 'balance', v_order.total - v_new_paid);
end;
$$;

create or replace function public.ww_update_order_status(
    p_business_id uuid, p_order_id uuid, p_new_status text, p_note text default null
) returns void
language plpgsql security definer set search_path = public
as $$
declare v_old_status text;
begin
    if p_new_status not in ('received','inspection','washing','ironing','ready','out_for_delivery','delivered','cancelled') then
        raise exception 'Invalid order status';
    end if;
    select status into v_old_status from public.orders where id = p_order_id and business_id = p_business_id for update;
    if not found then raise exception 'Order not found'; end if;
    update public.orders set status = p_new_status, updated_at = now() where id = p_order_id and business_id = p_business_id;
    insert into public.order_status_history(business_id, order_id, old_status, new_status, note)
    values (p_business_id, p_order_id, v_old_status, p_new_status, p_note);
end;
$$;

create or replace function public.ww_adjust_inventory(
    p_business_id uuid, p_item_id uuid, p_quantity_change numeric, p_note text default null
) returns jsonb
language plpgsql security definer set search_path = public
as $$
declare v_new_qty numeric(12,2);
begin
    if p_quantity_change is null or p_quantity_change = 0 then raise exception 'Quantity change cannot be zero'; end if;
    update public.inventory_items set quantity_on_hand = quantity_on_hand + p_quantity_change
    where id = p_item_id and business_id = p_business_id and quantity_on_hand + p_quantity_change >= 0
    returning quantity_on_hand into v_new_qty;
    if not found then raise exception 'Inventory item not found or insufficient stock'; end if;
    insert into public.inventory_movements(business_id, item_id, movement_type, quantity_change, note)
    values (p_business_id, p_item_id, case when p_quantity_change > 0 then 'stock_in' else 'stock_out' end, p_quantity_change, p_note);
    return jsonb_build_object('quantity_on_hand', v_new_qty);
end;
$$;

do $$
declare t text;
begin
  foreach t in array array[
    'businesses','customers','services','orders','order_items','payments',
    'order_status_history','inventory_items','inventory_movements','expenses'
  ] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on table public.%I from anon, authenticated', t);
    execute format('grant all on table public.%I to service_role', t);
  end loop;
end $$;

revoke all on function public.ww_create_order(uuid,text,text,text,timestamptz,jsonb,text) from public, anon, authenticated;
revoke all on function public.ww_record_payment(uuid,uuid,numeric,text,text) from public, anon, authenticated;
revoke all on function public.ww_update_order_status(uuid,uuid,text,text) from public, anon, authenticated;
revoke all on function public.ww_adjust_inventory(uuid,uuid,numeric,text) from public, anon, authenticated;
grant execute on function public.ww_create_order(uuid,text,text,text,timestamptz,jsonb,text) to service_role;
grant execute on function public.ww_record_payment(uuid,uuid,numeric,text,text) to service_role;
grant execute on function public.ww_update_order_status(uuid,uuid,text,text) to service_role;
grant execute on function public.ww_adjust_inventory(uuid,uuid,numeric,text) to service_role;

do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    begin alter publication supabase_realtime add table public.orders; exception when duplicate_object then null; end;
    begin alter publication supabase_realtime add table public.order_status_history; exception when duplicate_object then null; end;
  end if;
end $$;

comment on table public.businesses is 'One active business record per public no-login deployment.';
comment on table public.orders is 'Real laundry orders; public customer tracking is verified using order number and phone suffix.';
