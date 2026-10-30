-- ==========================================================================================
-- VISTA VMS: ISANG DATABASE FILE (schema + demo village)
--
-- Laman: 23 table ng system, at ang demo village na "Greenfield Village" para sa pag-test
--   (5 staff account, 6 bahay, 3 gate, 9 bisita). Password ng mga demo account: VistaDemo2026!
--
-- PARA I-IMPORT: gumawa ng bago at walang laman na database (hal. "vista"), buksan ang Query Tool,
--   buksan ang file na ito at pindutin ang F5.
--
-- PARA SA TOTOONG GAMIT (tanggalin ang demo data), patakbuhin sa Query Tool ang:
--       SELECT public.vista_remove_demo();
--   Mabubura ang demo village at lahat ng nakakabit dito. Mananatili ang mga table.
--   Pagkatapos, gumawa ng sarili mong village sa Super Admin (tingnan ang database/README.md).
-- ==========================================================================================

--
-- PostgreSQL database dump
--

-- Dumped from database version 16.2
-- Dumped by pg_dump version 16.2

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pgcrypto IS 'stub for local tests';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alerts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alerts (
    id bigint NOT NULL,
    property_id uuid NOT NULL,
    kind text NOT NULL,
    detail text NOT NULL,
    status text DEFAULT 'open'::text NOT NULL,
    visit_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT alerts_status_check CHECK ((status = ANY (ARRAY['open'::text, 'resolved'::text])))
);


--
-- Name: alerts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.alerts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: alerts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.alerts_id_seq OWNED BY public.alerts.id;


--
-- Name: audit_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_log (
    id bigint NOT NULL,
    property_id uuid NOT NULL,
    actor text NOT NULL,
    role text NOT NULL,
    action text NOT NULL,
    visit_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: audit_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.audit_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: audit_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.audit_log_id_seq OWNED BY public.audit_log.id;


--
-- Name: badges; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.badges (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    property_id uuid NOT NULL,
    code text NOT NULL,
    status text DEFAULT 'avail'::text NOT NULL,
    holder text,
    CONSTRAINT badges_status_check CHECK ((status = ANY (ARRAY['avail'::text, 'issued'::text, 'lost'::text])))
);


--
-- Name: gates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.gates (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    property_id uuid NOT NULL,
    name text NOT NULL,
    kind text DEFAULT 'Entry and exit'::text NOT NULL,
    active boolean DEFAULT true NOT NULL,
    pos_x real,
    pos_y real
);


--
-- Name: notifications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notifications (
    id bigint NOT NULL,
    property_id uuid NOT NULL,
    recipient text NOT NULL,
    subject text NOT NULL,
    status text DEFAULT 'sent'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: notifications_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.notifications_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: notifications_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.notifications_id_seq OWNED BY public.notifications.id;


--
-- Name: platform_audit; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_audit (
    id bigint NOT NULL,
    actor text NOT NULL,
    action text NOT NULL,
    property_id uuid,
    property text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: platform_audit_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.platform_audit_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: platform_audit_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.platform_audit_id_seq OWNED BY public.platform_audit.id;


--
-- Name: properties; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.properties (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    slug text NOT NULL,
    kind text DEFAULT 'village'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    active boolean DEFAULT true NOT NULL
);


--
-- Name: restricted_area_members; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.restricted_area_members (
    property_id uuid NOT NULL,
    area_id uuid NOT NULL,
    member_id uuid NOT NULL
);


--
-- Name: restricted_areas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.restricted_areas (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    property_id uuid NOT NULL,
    name text NOT NULL,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.settings (
    property_id uuid NOT NULL,
    key text NOT NULL,
    value jsonb NOT NULL
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    property_id uuid NOT NULL,
    email text NOT NULL,
    name text NOT NULL,
    role text NOT NULL,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    password_hash text,
    vista_token_version integer DEFAULT 0 NOT NULL,
    CONSTRAINT users_role_check CHECK ((role = ANY (ARRAY['admin'::text, 'guard'::text, 'hoa'::text, 'household'::text])))
);


--
-- Name: village_entry_photos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.village_entry_photos (
    visit_id uuid NOT NULL,
    property_id uuid NOT NULL,
    content bytea NOT NULL,
    content_type text DEFAULT 'image/jpeg'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    delete_after timestamp with time zone NOT NULL
);


--
-- Name: village_households; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.village_households (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    property_id uuid NOT NULL,
    lot_code text,
    owner_name text DEFAULT '(invited)'::text NOT NULL,
    holder_name text,
    email text,
    phone text,
    status text DEFAULT 'invited'::text NOT NULL,
    verified_at timestamp with time zone,
    verified_by text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT village_households_status_check CHECK ((status = ANY (ARRAY['invited'::text, 'awaiting'::text, 'verified'::text])))
);


--
-- Name: village_id_photos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.village_id_photos (
    visit_id uuid NOT NULL,
    property_id uuid NOT NULL,
    content bytea NOT NULL,
    content_type text DEFAULT 'image/jpeg'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    delete_after timestamp with time zone NOT NULL
);


--
-- Name: village_lots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.village_lots (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    property_id uuid NOT NULL,
    lot_code text NOT NULL,
    household_id uuid,
    pos_x real,
    pos_y real,
    route text
);


--
-- Name: village_maps; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.village_maps (
    property_id uuid NOT NULL,
    content bytea NOT NULL,
    content_type text NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: village_members; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.village_members (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    property_id uuid NOT NULL,
    household_id uuid NOT NULL,
    full_name text NOT NULL,
    is_minor boolean DEFAULT false NOT NULL
);


--
-- Name: village_vehicle_checks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.village_vehicle_checks (
    visit_id uuid NOT NULL,
    property_id uuid NOT NULL,
    photo_path text,
    plate_ok boolean DEFAULT false NOT NULL,
    color_ok boolean DEFAULT false NOT NULL,
    type_ok boolean DEFAULT false NOT NULL,
    override_used boolean DEFAULT false NOT NULL,
    override_reason text,
    checked_by text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    delete_after timestamp with time zone
);


--
-- Name: village_visit_details; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.village_visit_details (
    visit_id uuid NOT NULL,
    property_id uuid NOT NULL,
    household_id uuid,
    host_member_id uuid,
    visitor_name text NOT NULL,
    visitor_phone text NOT NULL,
    typed_house text NOT NULL,
    typed_host text DEFAULT ''::text NOT NULL,
    purpose text,
    visit_at timestamp with time zone,
    arrival_method text NOT NULL,
    declared_kind text,
    declared_color text,
    declared_plate text,
    restricted_flag boolean DEFAULT false NOT NULL,
    walk_in boolean DEFAULT false NOT NULL,
    gate_notified_at timestamp with time zone,
    vehicle_left boolean DEFAULT false NOT NULL,
    close_reason text,
    reject_reason text,
    email text,
    CONSTRAINT village_visit_details_arrival_method_check CHECK ((arrival_method = ANY (ARRAY['walking'::text, 'own_vehicle'::text, 'ride'::text])))
);


--
-- Name: village_visit_people; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.village_visit_people (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    property_id uuid NOT NULL,
    visit_id uuid NOT NULL,
    full_name text NOT NULL,
    is_lead boolean DEFAULT false NOT NULL,
    sort integer DEFAULT 0 NOT NULL,
    badge_id uuid,
    arrived_at timestamp with time zone,
    left_at timestamp with time zone
);


--
-- Name: visits; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.visits (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    property_id uuid NOT NULL,
    seq bigint NOT NULL,
    status text NOT NULL,
    qr_token text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT visits_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'queue'::text, 'walkin_pending'::text, 'approved'::text, 'at_gate'::text, 'arrived'::text, 'missing'::text, 'left'::text, 'closed'::text, 'declined'::text, 'rejected'::text, 'wrong_destination'::text])))
);


--
-- Name: visits_seq_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.visits ALTER COLUMN seq ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.visits_seq_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: vista_owned_tables; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vista_owned_tables (
    name text NOT NULL
);


--
-- Name: vista_schema_migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vista_schema_migrations (
    version text NOT NULL,
    applied_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: alerts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts ALTER COLUMN id SET DEFAULT nextval('public.alerts_id_seq'::regclass);


--
-- Name: audit_log id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log ALTER COLUMN id SET DEFAULT nextval('public.audit_log_id_seq'::regclass);


--
-- Name: notifications id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications ALTER COLUMN id SET DEFAULT nextval('public.notifications_id_seq'::regclass);


--
-- Name: platform_audit id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_audit ALTER COLUMN id SET DEFAULT nextval('public.platform_audit_id_seq'::regclass);


--
-- Data for Name: alerts; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.alerts VALUES (1, 'd8ef897f-d331-4409-9bbf-be7848b98940', 'Missing', 'VS-0006 Ana Flores: no house scan 3 hours after the gate notice', 'open', NULL, '2026-10-25 03:42:34.660348+00');


--
-- Data for Name: audit_log; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.audit_log VALUES (1, 'd8ef897f-d331-4409-9bbf-be7848b98940', 'Seed', 'Admin', 'Visit request VS-0001 created', 'a970944e-fb3a-489f-a496-1220e32dc160', '2026-10-25 03:42:34.660348+00');
INSERT INTO public.audit_log VALUES (2, 'd8ef897f-d331-4409-9bbf-be7848b98940', 'Seed', 'Admin', 'Visit request VS-0002 created', 'a5c67559-4893-4fee-b003-943bd0950edc', '2026-10-25 03:42:34.660348+00');
INSERT INTO public.audit_log VALUES (3, 'd8ef897f-d331-4409-9bbf-be7848b98940', 'Seed', 'Admin', 'Visit request VS-0003 created', '060e82fc-badc-4a35-8dc9-a1a0194bf0dc', '2026-10-25 03:42:34.660348+00');
INSERT INTO public.audit_log VALUES (4, 'd8ef897f-d331-4409-9bbf-be7848b98940', 'Seed', 'Admin', 'Visit request VS-0004 created', 'd3ce82ac-a588-4c66-9c7d-dbcd5bb6146e', '2026-10-25 03:42:34.660348+00');
INSERT INTO public.audit_log VALUES (5, 'd8ef897f-d331-4409-9bbf-be7848b98940', 'Seed', 'Admin', 'Visit request VS-0005 created', '010fb413-debc-4139-b2cf-89dca587f657', '2026-10-25 03:42:34.660348+00');
INSERT INTO public.audit_log VALUES (6, 'd8ef897f-d331-4409-9bbf-be7848b98940', 'Seed', 'Admin', 'Visit request VS-0006 created', '0c7a6b6c-e8d8-4fa9-a262-ab3c3f95baf9', '2026-10-25 03:42:34.660348+00');
INSERT INTO public.audit_log VALUES (7, 'd8ef897f-d331-4409-9bbf-be7848b98940', 'Seed', 'Admin', 'Visit request VS-0007 created', '8b4b353d-8a17-4f5b-ae29-5b55e911bb46', '2026-10-25 03:42:34.660348+00');
INSERT INTO public.audit_log VALUES (8, 'd8ef897f-d331-4409-9bbf-be7848b98940', 'Seed', 'Admin', 'Visit request VS-0008 created', 'c3fac37f-223c-44a7-bae6-c680f7e6bc94', '2026-10-25 03:42:34.660348+00');
INSERT INTO public.audit_log VALUES (9, 'd8ef897f-d331-4409-9bbf-be7848b98940', 'Seed', 'Admin', 'Visit request VS-0009 created', 'afcd6e75-cd40-43b0-8da4-7c1713b81e28', '2026-10-25 03:42:34.660348+00');
INSERT INTO public.audit_log VALUES (10, 'd8ef897f-d331-4409-9bbf-be7848b98940', 'Seed', 'System', 'Demo data loaded', NULL, '2026-10-25 03:42:34.660348+00');


--
-- Data for Name: badges; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.badges VALUES ('f4200155-800b-47d4-b688-c374b1793515', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'P06', 'avail', NULL);
INSERT INTO public.badges VALUES ('673528ce-0c90-4037-941c-0e3f6952166a', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'P07', 'avail', NULL);
INSERT INTO public.badges VALUES ('80f0fff6-2a8f-4b2c-a835-9002d92949fd', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'P08', 'avail', NULL);
INSERT INTO public.badges VALUES ('831b69ab-d263-4e8b-bdc4-d951734e0fc2', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'P09', 'avail', NULL);
INSERT INTO public.badges VALUES ('a4aac625-7de4-4000-b40f-533e0d4e17c6', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'P10', 'avail', NULL);
INSERT INTO public.badges VALUES ('63aba45f-e2f3-4159-bd91-9455698c2246', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'P11', 'avail', NULL);
INSERT INTO public.badges VALUES ('4f3bfc9c-1684-42c0-8403-a55f9af3b620', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'P12', 'avail', NULL);
INSERT INTO public.badges VALUES ('b3d5ae44-b485-47a3-95bd-b950b195b823', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'P13', 'avail', NULL);
INSERT INTO public.badges VALUES ('eaa0fb2e-04ef-4110-8a09-0f7ffbe1ab07', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'P14', 'avail', NULL);
INSERT INTO public.badges VALUES ('0b743982-1692-4716-a9fd-fab8e3211643', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'P01', 'issued', 'Dennis Uy');
INSERT INTO public.badges VALUES ('5c8f7e60-af0d-4859-ac6c-2c6f2f402f25', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'P02', 'issued', 'Dennis’s guest');
INSERT INTO public.badges VALUES ('8196316c-9b5a-44a8-b7b5-75b432c4b383', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'P03', 'issued', 'Paolo Lim');
INSERT INTO public.badges VALUES ('847d0ccc-8b65-4b50-a24e-c34cf7bc906e', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'P04', 'issued', 'Ana Flores');
INSERT INTO public.badges VALUES ('4f6f8c02-3678-48bf-aed3-8f527fdd2dbc', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'P05', 'avail', NULL);


--
-- Data for Name: gates; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.gates VALUES ('214de27c-2842-4f05-9c3f-55fcff21cd3c', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'Main gate', 'Entry and exit', true, NULL, NULL);
INSERT INTO public.gates VALUES ('e63ea652-1d0f-4968-862e-ecb5aba03638', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'Service gate', 'Deliveries', true, NULL, NULL);
INSERT INTO public.gates VALUES ('d2325437-7d19-4bfa-b83e-6e9d11bd850f', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'North pedestrian gate', 'Walk-ins', false, NULL, NULL);


--
-- Data for Name: notifications; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.notifications VALUES (1, 'd8ef897f-d331-4409-9bbf-be7848b98940', 'Maria Reyes', 'Approval link for VS-0001', 'sent', '2026-10-25 03:42:34.660348+00');
INSERT INTO public.notifications VALUES (2, 'd8ef897f-d331-4409-9bbf-be7848b98940', 'Ana Santos', 'Approval link for VS-0002', 'sent', '2026-10-25 03:42:34.660348+00');
INSERT INTO public.notifications VALUES (3, 'd8ef897f-d331-4409-9bbf-be7848b98940', 'Ana Santos', 'Approval link for VS-0003', 'sent', '2026-10-25 03:42:34.660348+00');
INSERT INTO public.notifications VALUES (4, 'd8ef897f-d331-4409-9bbf-be7848b98940', 'Maria Reyes', 'Approval link for VS-0004', 'sent', '2026-10-25 03:42:34.660348+00');
INSERT INTO public.notifications VALUES (5, 'd8ef897f-d331-4409-9bbf-be7848b98940', 'Ben Cruz', 'Approval link for VS-0005', 'sent', '2026-10-25 03:42:34.660348+00');
INSERT INTO public.notifications VALUES (6, 'd8ef897f-d331-4409-9bbf-be7848b98940', 'Rosa Dela Rosa', 'Approval link for VS-0006', 'sent', '2026-10-25 03:42:34.660348+00');
INSERT INTO public.notifications VALUES (7, 'd8ef897f-d331-4409-9bbf-be7848b98940', 'Ana Santos', 'Approval link for VS-0008', 'sent', '2026-10-25 03:42:34.660348+00');
INSERT INTO public.notifications VALUES (8, 'd8ef897f-d331-4409-9bbf-be7848b98940', 'Pia Garcia', 'Approval link for VS-0009', 'sent', '2026-10-25 03:42:34.660348+00');


--
-- Data for Name: platform_audit; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: properties; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.properties VALUES ('d8ef897f-d331-4409-9bbf-be7848b98940', 'Greenfield Village', 'greenfield-village-7f3a', 'village', '2026-10-25 03:42:34.660348+00', true);


--
-- Data for Name: restricted_area_members; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.restricted_area_members VALUES ('d8ef897f-d331-4409-9bbf-be7848b98940', 'acb9e698-81d7-4e11-b958-fa3c70294620', '155b8ade-c8b1-4c5f-962d-54c6d221fea8');
INSERT INTO public.restricted_area_members VALUES ('d8ef897f-d331-4409-9bbf-be7848b98940', 'a73a4a52-cb01-4229-8100-6f95f2f3bdba', '28ab42eb-e1da-430f-998e-b6084ea6d97c');


--
-- Data for Name: restricted_areas; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.restricted_areas VALUES ('acb9e698-81d7-4e11-b958-fa3c70294620', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'Care wing, Block 2', true, '2026-10-25 03:42:34.660348+00');
INSERT INTO public.restricted_areas VALUES ('a73a4a52-cb01-4229-8100-6f95f2f3bdba', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'Maintenance yard', true, '2026-10-25 03:42:34.660348+00');


--
-- Data for Name: settings; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.users VALUES ('058c8a4e-df1b-4f76-b54d-9ee6e4984f84', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'admin@greenfield.ph', 'Village Admin', 'admin', true, '2026-10-25 03:42:34.660348+00', 'scrypt$48d6946fff3fc45f402c9473226432d1$0eb61ba68d9c5829e624120160ed02e71e911e241d0a69394161138103101fab', 0);
INSERT INTO public.users VALUES ('d9246eaf-9578-4af3-a024-cd6d7b8904a0', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'ramon@greenfield.ph', 'Ramon Dela Cruz', 'guard', true, '2026-10-25 03:42:34.660348+00', 'scrypt$048cacb8bc8661422cde7c3069b69de8$8eee21b30e580e72573e1719c6833077a8b7347a686c0cdc7a35c2afd5f6a00b', 0);
INSERT INTO public.users VALUES ('0fc8dcfc-9b36-42ff-940e-3fddaaad5926', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'edgar@greenfield.ph', 'Edgar Santos', 'guard', true, '2026-10-25 03:42:34.660348+00', 'scrypt$617abef1b985c4f783684ce3ed749876$82ed169a6ec7feb4b27337a821558a09079d00bb66db6873ee248b316e5cdb25', 0);
INSERT INTO public.users VALUES ('69ed3c83-f71e-49a0-b3ff-ad177ed49926', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'hoa@greenfield.ph', 'HOA desk', 'hoa', true, '2026-10-25 03:42:34.660348+00', 'scrypt$50d9dc82b298f24b447a06ed3deb7d9c$73aee4ad112c2808597ed0adbab56720d8a5b9945c05af16fa8e4a1860c2b729', 0);
INSERT INTO public.users VALUES ('51fd258a-dcde-4e70-8052-278031b842b1', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'lorna@greenfield.ph', 'Lorna Aquino', 'hoa', true, '2026-10-25 03:42:34.660348+00', 'scrypt$4f5f2596bfb7c1474afa01f21c3a1d0a$3073bab0729d2a3fae74ec2e7f27a9e51b324355dba8e52bb415d4ff37a1ea9c', 0);


--
-- Data for Name: village_entry_photos; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: village_households; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.village_households VALUES ('a976d514-5769-4cdd-a8df-16574a25220c', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'B1-L4', 'Reyes', 'Maria Reyes', 'maria@mail.ph', '0917 555 0100', 'verified', '2026-10-25 03:42:34.660348+00', NULL, '2026-10-25 03:42:34.660348+00');
INSERT INTO public.village_households VALUES ('1ccf10c6-6094-47cd-9f3f-5c5caaa0487c', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'B2-L7', 'Santos', 'Ana Santos', 'ana@mail.ph', '0917 555 0101', 'verified', '2026-10-25 03:42:34.660348+00', NULL, '2026-10-25 03:42:34.660348+00');
INSERT INTO public.village_households VALUES ('73bf59d0-5b70-451e-8fb1-cc9565f7484b', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'B3-L2', 'Cruz', 'Ben Cruz', 'ben@mail.ph', '0917 555 0102', 'awaiting', NULL, NULL, '2026-10-25 03:42:34.660348+00');
INSERT INTO public.village_households VALUES ('3279a4cf-c6f4-431d-97ea-809d4fe9cf7b', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'B2-L2', 'Dela Rosa', 'Rosa Dela Rosa', 'rosa@mail.ph', '0917 555 0103', 'verified', '2026-10-25 03:42:34.660348+00', NULL, '2026-10-25 03:42:34.660348+00');
INSERT INTO public.village_households VALUES ('38d80af2-8b64-4d2b-98da-0615a129a753', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'B3-L5', 'Garcia', 'Pia Garcia', 'pia@mail.ph', '0917 555 0104', 'awaiting', NULL, NULL, '2026-10-25 03:42:34.660348+00');
INSERT INTO public.village_households VALUES ('3f347413-4695-4681-877a-ffff7925ba7b', 'd8ef897f-d331-4409-9bbf-be7848b98940', NULL, '(invited)', 'lim@mail.ph', 'lim@mail.ph', NULL, 'invited', NULL, NULL, '2026-10-25 03:42:34.660348+00');


--
-- Data for Name: village_id_photos; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: village_lots; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.village_lots VALUES ('ce9085ac-6db4-4bd2-b08c-2e864087926c', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'B1-L4', 'a976d514-5769-4cdd-a8df-16574a25220c', NULL, NULL, NULL);
INSERT INTO public.village_lots VALUES ('42bde876-da93-416d-bce4-5a3748dbaec3', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'B2-L7', '1ccf10c6-6094-47cd-9f3f-5c5caaa0487c', NULL, NULL, NULL);
INSERT INTO public.village_lots VALUES ('d9e58266-173b-4729-bb1d-4160ecb66054', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'B3-L2', '73bf59d0-5b70-451e-8fb1-cc9565f7484b', NULL, NULL, NULL);
INSERT INTO public.village_lots VALUES ('8f580676-616b-44a5-88f9-ba40002b8c7e', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'B2-L2', '3279a4cf-c6f4-431d-97ea-809d4fe9cf7b', NULL, NULL, NULL);
INSERT INTO public.village_lots VALUES ('2c577307-dbc3-45bc-9540-35e01d331e40', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'B3-L5', '38d80af2-8b64-4d2b-98da-0615a129a753', NULL, NULL, NULL);
INSERT INTO public.village_lots VALUES ('0622f3fb-c578-4a18-abc9-5a55a154a69b', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'B1-L1', NULL, NULL, NULL, NULL);


--
-- Data for Name: village_maps; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: village_members; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.village_members VALUES ('eb60fb02-18b5-48bf-a063-2c267ed31945', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'a976d514-5769-4cdd-a8df-16574a25220c', 'Maria Reyes', false);
INSERT INTO public.village_members VALUES ('e805387a-b681-438a-a2be-4267756655ae', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'a976d514-5769-4cdd-a8df-16574a25220c', 'Lito Reyes', false);
INSERT INTO public.village_members VALUES ('b8036058-f8d3-4212-9874-728c6d33af62', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'a976d514-5769-4cdd-a8df-16574a25220c', 'Paolo Reyes', true);
INSERT INTO public.village_members VALUES ('1d3927ef-495f-4f34-8bb8-11f41d8b27e7', 'd8ef897f-d331-4409-9bbf-be7848b98940', '1ccf10c6-6094-47cd-9f3f-5c5caaa0487c', 'Ana Santos', false);
INSERT INTO public.village_members VALUES ('155b8ade-c8b1-4c5f-962d-54c6d221fea8', 'd8ef897f-d331-4409-9bbf-be7848b98940', '1ccf10c6-6094-47cd-9f3f-5c5caaa0487c', 'Jun Santos', false);
INSERT INTO public.village_members VALUES ('10b3074b-2e08-4cd7-9c4c-848f72ffe8e2', 'd8ef897f-d331-4409-9bbf-be7848b98940', '1ccf10c6-6094-47cd-9f3f-5c5caaa0487c', 'Mika Santos', true);
INSERT INTO public.village_members VALUES ('28ab42eb-e1da-430f-998e-b6084ea6d97c', 'd8ef897f-d331-4409-9bbf-be7848b98940', '73bf59d0-5b70-451e-8fb1-cc9565f7484b', 'Ben Cruz', false);
INSERT INTO public.village_members VALUES ('1e44ecbb-1c0f-4fe4-90b6-6df9796651ca', 'd8ef897f-d331-4409-9bbf-be7848b98940', '3279a4cf-c6f4-431d-97ea-809d4fe9cf7b', 'Rosa Dela Rosa', false);
INSERT INTO public.village_members VALUES ('4645ec18-7978-4f42-b7d1-2a25fd9ac818', 'd8ef897f-d331-4409-9bbf-be7848b98940', '38d80af2-8b64-4d2b-98da-0615a129a753', 'Pia Garcia', false);
INSERT INTO public.village_members VALUES ('10b3422d-ba45-4cfa-ab0b-0860fb3f8c9d', 'd8ef897f-d331-4409-9bbf-be7848b98940', '38d80af2-8b64-4d2b-98da-0615a129a753', 'Gio Garcia', false);


--
-- Data for Name: village_vehicle_checks; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.village_vehicle_checks VALUES ('010fb413-debc-4139-b2cf-89dca587f657', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'entry-photos/demo.jpg', true, true, true, false, NULL, NULL, '2026-10-25 03:42:34.660348+00', NULL);


--
-- Data for Name: village_visit_details; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.village_visit_details VALUES ('a970944e-fb3a-489f-a496-1220e32dc160', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'a976d514-5769-4cdd-a8df-16574a25220c', 'eb60fb02-18b5-48bf-a063-2c267ed31945', 'Rico Mendoza', '0917 555 0114', 'B1-L4', 'Maria Reyes', 'Visit', NULL, 'own_vehicle', '', '', '', false, false, NULL, false, NULL, NULL, NULL);
INSERT INTO public.village_visit_details VALUES ('a5c67559-4893-4fee-b003-943bd0950edc', 'd8ef897f-d331-4409-9bbf-be7848b98940', '1ccf10c6-6094-47cd-9f3f-5c5caaa0487c', '1d3927ef-495f-4f34-8bb8-11f41d8b27e7', 'Carla Bautista', '0917 555 0113', 'B2-L7', 'Ana Santos', 'Visit', NULL, 'walking', '', '', '', false, false, NULL, false, NULL, NULL, NULL);
INSERT INTO public.village_visit_details VALUES ('060e82fc-badc-4a35-8dc9-a1a0194bf0dc', 'd8ef897f-d331-4409-9bbf-be7848b98940', '1ccf10c6-6094-47cd-9f3f-5c5caaa0487c', '155b8ade-c8b1-4c5f-962d-54c6d221fea8', 'Grace Tan', '0917 555 0111', 'B2-L7', 'Jun Santos', 'Visit', NULL, 'walking', '', '', '', true, false, NULL, false, NULL, NULL, NULL);
INSERT INTO public.village_visit_details VALUES ('d3ce82ac-a588-4c66-9c7d-dbcd5bb6146e', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'a976d514-5769-4cdd-a8df-16574a25220c', 'e805387a-b681-438a-a2be-4267756655ae', 'Dennis Uy', '0917 555 0112', 'B1-L4', 'Lito Reyes', 'Visit', NULL, 'ride', '', '', '', false, false, '2026-10-25 02:42:34.967454+00', false, NULL, NULL, NULL);
INSERT INTO public.village_visit_details VALUES ('010fb413-debc-4139-b2cf-89dca587f657', 'd8ef897f-d331-4409-9bbf-be7848b98940', '73bf59d0-5b70-451e-8fb1-cc9565f7484b', NULL, 'Paolo Lim', '0917 555 0110', 'B3-L2', '', 'Visit', NULL, 'own_vehicle', '', '', '', false, false, '2026-10-25 02:42:34.970349+00', false, NULL, NULL, NULL);
INSERT INTO public.village_visit_details VALUES ('0c7a6b6c-e8d8-4fa9-a262-ab3c3f95baf9', 'd8ef897f-d331-4409-9bbf-be7848b98940', '3279a4cf-c6f4-431d-97ea-809d4fe9cf7b', '1e44ecbb-1c0f-4fe4-90b6-6df9796651ca', 'Ana Flores', '0917 555 0108', 'B2-L2', 'Rosa Dela Rosa', 'Visit', NULL, 'walking', '', '', '', false, false, '2026-10-24 23:42:34.974654+00', false, NULL, NULL, NULL);
INSERT INTO public.village_visit_details VALUES ('8b4b353d-8a17-4f5b-ae29-5b55e911bb46', 'd8ef897f-d331-4409-9bbf-be7848b98940', NULL, NULL, 'Tess Villanueva', '0917 555 0107', 'B1-L99', 'Maria Reyes', 'Visit', NULL, 'walking', '', '', '', false, false, NULL, false, NULL, NULL, NULL);
INSERT INTO public.village_visit_details VALUES ('c3fac37f-223c-44a7-bae6-c680f7e6bc94', 'd8ef897f-d331-4409-9bbf-be7848b98940', '1ccf10c6-6094-47cd-9f3f-5c5caaa0487c', '1d3927ef-495f-4f34-8bb8-11f41d8b27e7', 'Ken Aquino', '0917 555 0106', 'B2-L7', 'Ana Santos', 'Visit', NULL, 'ride', '', '', '', false, false, '2026-10-24 22:42:34.977344+00', false, NULL, NULL, NULL);
INSERT INTO public.village_visit_details VALUES ('afcd6e75-cd40-43b0-8da4-7c1713b81e28', 'd8ef897f-d331-4409-9bbf-be7848b98940', '38d80af2-8b64-4d2b-98da-0615a129a753', '4645ec18-7978-4f42-b7d1-2a25fd9ac818', 'Liza Ramos', '0917 555 0105', 'B3-L5', 'Pia Garcia', 'Visit', NULL, 'walking', '', '', '', false, false, NULL, false, NULL, NULL, NULL);


--
-- Data for Name: village_visit_people; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.village_visit_people VALUES ('49e3ba14-9866-4c0b-a0c8-0e79729a36ef', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'a970944e-fb3a-489f-a496-1220e32dc160', 'Rico Mendoza', true, 0, NULL, NULL, NULL);
INSERT INTO public.village_visit_people VALUES ('23eaaf92-7f7b-459b-9bd6-94dc853b9da9', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'a970944e-fb3a-489f-a496-1220e32dc160', 'Rico’s guest 1', false, 1, NULL, NULL, NULL);
INSERT INTO public.village_visit_people VALUES ('0c6cf9f1-494d-4991-874b-fa0b4c89b7fa', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'a970944e-fb3a-489f-a496-1220e32dc160', 'Rico’s guest 2', false, 2, NULL, NULL, NULL);
INSERT INTO public.village_visit_people VALUES ('4a787630-65e1-43c5-9f4d-e5c2fe1ff8f6', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'a5c67559-4893-4fee-b003-943bd0950edc', 'Carla Bautista', true, 0, NULL, NULL, NULL);
INSERT INTO public.village_visit_people VALUES ('432a0467-60ed-4ac6-9727-a5deeef68ce7', 'd8ef897f-d331-4409-9bbf-be7848b98940', '060e82fc-badc-4a35-8dc9-a1a0194bf0dc', 'Grace Tan', true, 0, NULL, NULL, NULL);
INSERT INTO public.village_visit_people VALUES ('69efd687-2251-4b9e-9270-af0c074a85ca', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'd3ce82ac-a588-4c66-9c7d-dbcd5bb6146e', 'Dennis Uy', true, 0, '0b743982-1692-4716-a9fd-fab8e3211643', NULL, NULL);
INSERT INTO public.village_visit_people VALUES ('851b49ae-a240-442b-9db2-8a1f835342eb', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'd3ce82ac-a588-4c66-9c7d-dbcd5bb6146e', 'Dennis’s guest', false, 1, '5c8f7e60-af0d-4859-ac6c-2c6f2f402f25', NULL, NULL);
INSERT INTO public.village_visit_people VALUES ('c365eb8c-62bb-486c-a3f2-c6e3015509cb', 'd8ef897f-d331-4409-9bbf-be7848b98940', '010fb413-debc-4139-b2cf-89dca587f657', 'Paolo Lim', true, 0, '8196316c-9b5a-44a8-b7b5-75b432c4b383', '2026-10-25 03:42:34.660348+00', NULL);
INSERT INTO public.village_visit_people VALUES ('62668041-d7e0-4a9a-b776-5bd3fb47069e', 'd8ef897f-d331-4409-9bbf-be7848b98940', '0c7a6b6c-e8d8-4fa9-a262-ab3c3f95baf9', 'Ana Flores', true, 0, '847d0ccc-8b65-4b50-a24e-c34cf7bc906e', NULL, NULL);
INSERT INTO public.village_visit_people VALUES ('d30bcc0f-029f-4677-8b8b-9992350d51bb', 'd8ef897f-d331-4409-9bbf-be7848b98940', '8b4b353d-8a17-4f5b-ae29-5b55e911bb46', 'Tess Villanueva', true, 0, NULL, NULL, NULL);
INSERT INTO public.village_visit_people VALUES ('633bc0aa-d362-4615-ab86-bb10bb4cf54f', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'c3fac37f-223c-44a7-bae6-c680f7e6bc94', 'Ken Aquino', true, 0, '4f6f8c02-3678-48bf-aed3-8f527fdd2dbc', NULL, '2026-10-25 03:42:34.660348+00');
INSERT INTO public.village_visit_people VALUES ('5ac10e5d-4c92-4d69-a0c4-c4e397d7fefb', 'd8ef897f-d331-4409-9bbf-be7848b98940', 'afcd6e75-cd40-43b0-8da4-7c1713b81e28', 'Liza Ramos', true, 0, NULL, NULL, NULL);


--
-- Data for Name: visits; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.visits OVERRIDING SYSTEM VALUE VALUES ('a970944e-fb3a-489f-a496-1220e32dc160', 'd8ef897f-d331-4409-9bbf-be7848b98940', 1, 'approved', 'tW5cPDlmMPRs', '2026-10-25 03:42:34.660348+00');
INSERT INTO public.visits OVERRIDING SYSTEM VALUE VALUES ('a5c67559-4893-4fee-b003-943bd0950edc', 'd8ef897f-d331-4409-9bbf-be7848b98940', 2, 'pending', 'Cugg9sUEjLL1', '2026-10-25 03:42:34.660348+00');
INSERT INTO public.visits OVERRIDING SYSTEM VALUE VALUES ('060e82fc-badc-4a35-8dc9-a1a0194bf0dc', 'd8ef897f-d331-4409-9bbf-be7848b98940', 3, 'approved', 'P3fV91aCCLXP', '2026-10-25 03:42:34.660348+00');
INSERT INTO public.visits OVERRIDING SYSTEM VALUE VALUES ('d3ce82ac-a588-4c66-9c7d-dbcd5bb6146e', 'd8ef897f-d331-4409-9bbf-be7848b98940', 4, 'at_gate', 'UCzpCyAfmu_q', '2026-10-25 03:42:34.660348+00');
INSERT INTO public.visits OVERRIDING SYSTEM VALUE VALUES ('010fb413-debc-4139-b2cf-89dca587f657', 'd8ef897f-d331-4409-9bbf-be7848b98940', 5, 'arrived', 'F-2S468UXp-3', '2026-10-25 03:42:34.660348+00');
INSERT INTO public.visits OVERRIDING SYSTEM VALUE VALUES ('0c7a6b6c-e8d8-4fa9-a262-ab3c3f95baf9', 'd8ef897f-d331-4409-9bbf-be7848b98940', 6, 'missing', 'kZpXb6r5tDdC', '2026-10-25 03:42:34.660348+00');
INSERT INTO public.visits OVERRIDING SYSTEM VALUE VALUES ('8b4b353d-8a17-4f5b-ae29-5b55e911bb46', 'd8ef897f-d331-4409-9bbf-be7848b98940', 7, 'queue', 'T_Kh2YlbxHR3', '2026-10-25 03:42:34.660348+00');
INSERT INTO public.visits OVERRIDING SYSTEM VALUE VALUES ('c3fac37f-223c-44a7-bae6-c680f7e6bc94', 'd8ef897f-d331-4409-9bbf-be7848b98940', 8, 'left', 'FoXuru4w8o7h', '2026-10-25 03:42:34.660348+00');
INSERT INTO public.visits OVERRIDING SYSTEM VALUE VALUES ('afcd6e75-cd40-43b0-8da4-7c1713b81e28', 'd8ef897f-d331-4409-9bbf-be7848b98940', 9, 'declined', 'OCli3hTkKqcT', '2026-10-25 03:42:34.660348+00');


--
-- Data for Name: vista_owned_tables; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.vista_owned_tables VALUES ('alerts');
INSERT INTO public.vista_owned_tables VALUES ('audit_log');
INSERT INTO public.vista_owned_tables VALUES ('badges');
INSERT INTO public.vista_owned_tables VALUES ('gates');
INSERT INTO public.vista_owned_tables VALUES ('notifications');
INSERT INTO public.vista_owned_tables VALUES ('properties');
INSERT INTO public.vista_owned_tables VALUES ('settings');
INSERT INTO public.vista_owned_tables VALUES ('users');
INSERT INTO public.vista_owned_tables VALUES ('visits');
INSERT INTO public.vista_owned_tables VALUES ('restricted_area_members');
INSERT INTO public.vista_owned_tables VALUES ('restricted_areas');
INSERT INTO public.vista_owned_tables VALUES ('village_households');
INSERT INTO public.vista_owned_tables VALUES ('village_lots');
INSERT INTO public.vista_owned_tables VALUES ('village_members');
INSERT INTO public.vista_owned_tables VALUES ('village_vehicle_checks');
INSERT INTO public.vista_owned_tables VALUES ('village_visit_details');
INSERT INTO public.vista_owned_tables VALUES ('village_visit_people');
INSERT INTO public.vista_owned_tables VALUES ('village_entry_photos');
INSERT INTO public.vista_owned_tables VALUES ('village_id_photos');
INSERT INTO public.vista_owned_tables VALUES ('village_maps');
INSERT INTO public.vista_owned_tables VALUES ('platform_audit');


--
-- Data for Name: vista_schema_migrations; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.vista_schema_migrations VALUES ('0001_foundation.sql', '2026-10-25 03:42:34.527644+00');
INSERT INTO public.vista_schema_migrations VALUES ('0002_village.sql', '2026-10-25 03:42:34.569956+00');
INSERT INTO public.vista_schema_migrations VALUES ('0003_rls.sql', '2026-10-25 03:42:34.601484+00');
INSERT INTO public.vista_schema_migrations VALUES ('0004_entry_photos_and_host_fk.sql', '2026-10-25 03:42:34.614055+00');
INSERT INTO public.vista_schema_migrations VALUES ('0005_visitor_id_photos.sql', '2026-10-25 03:42:34.622072+00');
INSERT INTO public.vista_schema_migrations VALUES ('0006_admin_map.sql', '2026-10-25 03:42:34.627325+00');
INSERT INTO public.vista_schema_migrations VALUES ('0007_visitor_email.sql', '2026-10-25 03:42:34.631952+00');
INSERT INTO public.vista_schema_migrations VALUES ('0008_platform.sql', '2026-10-25 03:42:34.633506+00');
INSERT INTO public.vista_schema_migrations VALUES ('0009_staff_passwords.sql', '2026-10-25 03:42:34.640239+00');
INSERT INTO public.vista_schema_migrations VALUES ('0010_token_version.sql', '2026-10-25 03:42:34.645719+00');


--
-- Name: alerts_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.alerts_id_seq', 1, true);


--
-- Name: audit_log_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.audit_log_id_seq', 10, true);


--
-- Name: notifications_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.notifications_id_seq', 8, true);


--
-- Name: platform_audit_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.platform_audit_id_seq', 1, false);


--
-- Name: visits_seq_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.visits_seq_seq', 9, true);


--
-- Name: alerts alerts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_pkey PRIMARY KEY (id);


--
-- Name: audit_log audit_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT audit_log_pkey PRIMARY KEY (id);


--
-- Name: badges badges_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.badges
    ADD CONSTRAINT badges_pkey PRIMARY KEY (id);


--
-- Name: badges badges_property_id_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.badges
    ADD CONSTRAINT badges_property_id_code_key UNIQUE (property_id, code);


--
-- Name: gates gates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gates
    ADD CONSTRAINT gates_pkey PRIMARY KEY (id);


--
-- Name: notifications notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);


--
-- Name: platform_audit platform_audit_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_audit
    ADD CONSTRAINT platform_audit_pkey PRIMARY KEY (id);


--
-- Name: properties properties_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.properties
    ADD CONSTRAINT properties_pkey PRIMARY KEY (id);


--
-- Name: properties properties_slug_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.properties
    ADD CONSTRAINT properties_slug_key UNIQUE (slug);


--
-- Name: restricted_area_members restricted_area_members_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.restricted_area_members
    ADD CONSTRAINT restricted_area_members_pkey PRIMARY KEY (area_id, member_id);


--
-- Name: restricted_areas restricted_areas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.restricted_areas
    ADD CONSTRAINT restricted_areas_pkey PRIMARY KEY (id);


--
-- Name: settings settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.settings
    ADD CONSTRAINT settings_pkey PRIMARY KEY (property_id, key);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: village_entry_photos village_entry_photos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.village_entry_photos
    ADD CONSTRAINT village_entry_photos_pkey PRIMARY KEY (visit_id);


--
-- Name: village_households village_households_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.village_households
    ADD CONSTRAINT village_households_pkey PRIMARY KEY (id);


--
-- Name: village_id_photos village_id_photos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.village_id_photos
    ADD CONSTRAINT village_id_photos_pkey PRIMARY KEY (visit_id);


--
-- Name: village_lots village_lots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.village_lots
    ADD CONSTRAINT village_lots_pkey PRIMARY KEY (id);


--
-- Name: village_maps village_maps_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.village_maps
    ADD CONSTRAINT village_maps_pkey PRIMARY KEY (property_id);


--
-- Name: village_members village_members_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.village_members
    ADD CONSTRAINT village_members_pkey PRIMARY KEY (id);


--
-- Name: village_vehicle_checks village_vehicle_checks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.village_vehicle_checks
    ADD CONSTRAINT village_vehicle_checks_pkey PRIMARY KEY (visit_id);


--
-- Name: village_visit_details village_visit_details_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.village_visit_details
    ADD CONSTRAINT village_visit_details_pkey PRIMARY KEY (visit_id);


--
-- Name: village_visit_people village_visit_people_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.village_visit_people
    ADD CONSTRAINT village_visit_people_pkey PRIMARY KEY (id);


--
-- Name: visits visits_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.visits
    ADD CONSTRAINT visits_pkey PRIMARY KEY (id);


--
-- Name: visits visits_qr_token_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.visits
    ADD CONSTRAINT visits_qr_token_key UNIQUE (qr_token);


--
-- Name: vista_owned_tables vista_owned_tables_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vista_owned_tables
    ADD CONSTRAINT vista_owned_tables_pkey PRIMARY KEY (name);


--
-- Name: vista_schema_migrations vista_schema_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vista_schema_migrations
    ADD CONSTRAINT vista_schema_migrations_pkey PRIMARY KEY (version);


--
-- Name: ix_audit_prop_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_prop_time ON public.audit_log USING btree (property_id, created_at DESC);


--
-- Name: ix_vep_delete_after; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vep_delete_after ON public.village_entry_photos USING btree (delete_after);


--
-- Name: ix_vip_delete_after; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vip_delete_after ON public.village_id_photos USING btree (delete_after);


--
-- Name: ix_visits_prop_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_visits_prop_status ON public.visits USING btree (property_id, status);


--
-- Name: ix_vm_hh; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vm_hh ON public.village_members USING btree (property_id, household_id);


--
-- Name: ix_vvd_hh; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vvd_hh ON public.village_visit_details USING btree (property_id, household_id);


--
-- Name: ix_vvd_phone; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vvd_phone ON public.village_visit_details USING btree (property_id, visitor_phone);


--
-- Name: ix_vvp_visit; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vvp_visit ON public.village_visit_people USING btree (property_id, visit_id);


--
-- Name: ux_one_admin_per_property; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ux_one_admin_per_property ON public.users USING btree (property_id) WHERE (role = 'admin'::text);


--
-- Name: ux_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ux_users_email ON public.users USING btree (property_id, lower(email));


--
-- Name: ux_vh_lot; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ux_vh_lot ON public.village_households USING btree (property_id, lower(lot_code)) WHERE (lot_code IS NOT NULL);


--
-- Name: ux_visits_prop_seq; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ux_visits_prop_seq ON public.visits USING btree (property_id, seq);


--
-- Name: ux_vl_lot; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ux_vl_lot ON public.village_lots USING btree (property_id, lower(lot_code));


--
-- Name: alerts alerts_property_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_property_id_fkey FOREIGN KEY (property_id) REFERENCES public.properties(id) ON DELETE CASCADE;


--
-- Name: audit_log audit_log_property_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT audit_log_property_id_fkey FOREIGN KEY (property_id) REFERENCES public.properties(id) ON DELETE CASCADE;


--
-- Name: badges badges_property_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.badges
    ADD CONSTRAINT badges_property_id_fkey FOREIGN KEY (property_id) REFERENCES public.properties(id) ON DELETE CASCADE;


--
-- Name: gates gates_property_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gates
    ADD CONSTRAINT gates_property_id_fkey FOREIGN KEY (property_id) REFERENCES public.properties(id) ON DELETE CASCADE;


--
-- Name: notifications notifications_property_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_property_id_fkey FOREIGN KEY (property_id) REFERENCES public.properties(id) ON DELETE CASCADE;


--
-- Name: platform_audit platform_audit_property_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_audit
    ADD CONSTRAINT platform_audit_property_id_fkey FOREIGN KEY (property_id) REFERENCES public.properties(id) ON DELETE SET NULL;


--
-- Name: restricted_area_members restricted_area_members_area_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.restricted_area_members
    ADD CONSTRAINT restricted_area_members_area_id_fkey FOREIGN KEY (area_id) REFERENCES public.restricted_areas(id) ON DELETE CASCADE;


--
-- Name: restricted_area_members restricted_area_members_member_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.restricted_area_members
    ADD CONSTRAINT restricted_area_members_member_id_fkey FOREIGN KEY (member_id) REFERENCES public.village_members(id) ON DELETE CASCADE;


--
-- Name: restricted_area_members restricted_area_members_property_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.restricted_area_members
    ADD CONSTRAINT restricted_area_members_property_id_fkey FOREIGN KEY (property_id) REFERENCES public.properties(id) ON DELETE CASCADE;


--
-- Name: restricted_areas restricted_areas_property_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.restricted_areas
    ADD CONSTRAINT restricted_areas_property_id_fkey FOREIGN KEY (property_id) REFERENCES public.properties(id) ON DELETE CASCADE;


--
-- Name: settings settings_property_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.settings
    ADD CONSTRAINT settings_property_id_fkey FOREIGN KEY (property_id) REFERENCES public.properties(id) ON DELETE CASCADE;


--
-- Name: users users_property_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_property_id_fkey FOREIGN KEY (property_id) REFERENCES public.properties(id) ON DELETE CASCADE;


--
-- Name: village_entry_photos village_entry_photos_property_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.village_entry_photos
    ADD CONSTRAINT village_entry_photos_property_id_fkey FOREIGN KEY (property_id) REFERENCES public.properties(id) ON DELETE CASCADE;


--
-- Name: village_entry_photos village_entry_photos_visit_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.village_entry_photos
    ADD CONSTRAINT village_entry_photos_visit_id_fkey FOREIGN KEY (visit_id) REFERENCES public.visits(id) ON DELETE CASCADE;


--
-- Name: village_households village_households_property_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.village_households
    ADD CONSTRAINT village_households_property_id_fkey FOREIGN KEY (property_id) REFERENCES public.properties(id) ON DELETE CASCADE;


--
-- Name: village_id_photos village_id_photos_property_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.village_id_photos
    ADD CONSTRAINT village_id_photos_property_id_fkey FOREIGN KEY (property_id) REFERENCES public.properties(id) ON DELETE CASCADE;


--
-- Name: village_id_photos village_id_photos_visit_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.village_id_photos
    ADD CONSTRAINT village_id_photos_visit_id_fkey FOREIGN KEY (visit_id) REFERENCES public.visits(id) ON DELETE CASCADE;


--
-- Name: village_lots village_lots_household_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.village_lots
    ADD CONSTRAINT village_lots_household_id_fkey FOREIGN KEY (household_id) REFERENCES public.village_households(id) ON DELETE SET NULL;


--
-- Name: village_lots village_lots_property_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.village_lots
    ADD CONSTRAINT village_lots_property_id_fkey FOREIGN KEY (property_id) REFERENCES public.properties(id) ON DELETE CASCADE;


--
-- Name: village_maps village_maps_property_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.village_maps
    ADD CONSTRAINT village_maps_property_id_fkey FOREIGN KEY (property_id) REFERENCES public.properties(id) ON DELETE CASCADE;


--
-- Name: village_members village_members_household_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.village_members
    ADD CONSTRAINT village_members_household_id_fkey FOREIGN KEY (household_id) REFERENCES public.village_households(id) ON DELETE CASCADE;


--
-- Name: village_members village_members_property_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.village_members
    ADD CONSTRAINT village_members_property_id_fkey FOREIGN KEY (property_id) REFERENCES public.properties(id) ON DELETE CASCADE;


--
-- Name: village_vehicle_checks village_vehicle_checks_property_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.village_vehicle_checks
    ADD CONSTRAINT village_vehicle_checks_property_id_fkey FOREIGN KEY (property_id) REFERENCES public.properties(id) ON DELETE CASCADE;


--
-- Name: village_vehicle_checks village_vehicle_checks_visit_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.village_vehicle_checks
    ADD CONSTRAINT village_vehicle_checks_visit_id_fkey FOREIGN KEY (visit_id) REFERENCES public.visits(id) ON DELETE CASCADE;


--
-- Name: village_visit_details village_visit_details_host_member_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.village_visit_details
    ADD CONSTRAINT village_visit_details_host_member_id_fkey FOREIGN KEY (host_member_id) REFERENCES public.village_members(id) ON DELETE SET NULL;


--
-- Name: village_visit_details village_visit_details_household_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.village_visit_details
    ADD CONSTRAINT village_visit_details_household_id_fkey FOREIGN KEY (household_id) REFERENCES public.village_households(id);


--
-- Name: village_visit_details village_visit_details_property_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.village_visit_details
    ADD CONSTRAINT village_visit_details_property_id_fkey FOREIGN KEY (property_id) REFERENCES public.properties(id) ON DELETE CASCADE;


--
-- Name: village_visit_details village_visit_details_visit_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.village_visit_details
    ADD CONSTRAINT village_visit_details_visit_id_fkey FOREIGN KEY (visit_id) REFERENCES public.visits(id) ON DELETE CASCADE;


--
-- Name: village_visit_people village_visit_people_badge_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.village_visit_people
    ADD CONSTRAINT village_visit_people_badge_id_fkey FOREIGN KEY (badge_id) REFERENCES public.badges(id);


--
-- Name: village_visit_people village_visit_people_property_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.village_visit_people
    ADD CONSTRAINT village_visit_people_property_id_fkey FOREIGN KEY (property_id) REFERENCES public.properties(id) ON DELETE CASCADE;


--
-- Name: village_visit_people village_visit_people_visit_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.village_visit_people
    ADD CONSTRAINT village_visit_people_visit_id_fkey FOREIGN KEY (visit_id) REFERENCES public.visits(id) ON DELETE CASCADE;


--
-- Name: visits visits_property_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.visits
    ADD CONSTRAINT visits_property_id_fkey FOREIGN KEY (property_id) REFERENCES public.properties(id) ON DELETE CASCADE;


--
-- Name: alerts; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.alerts ENABLE ROW LEVEL SECURITY;

--
-- Name: audit_log; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;

--
-- Name: badges; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.badges ENABLE ROW LEVEL SECURITY;

--
-- Name: gates; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.gates ENABLE ROW LEVEL SECURITY;

--
-- Name: notifications; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;

--
-- Name: platform_audit; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.platform_audit ENABLE ROW LEVEL SECURITY;

--
-- Name: properties; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.properties ENABLE ROW LEVEL SECURITY;

--
-- Name: restricted_area_members; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.restricted_area_members ENABLE ROW LEVEL SECURITY;

--
-- Name: restricted_areas; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.restricted_areas ENABLE ROW LEVEL SECURITY;

--
-- Name: settings; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.settings ENABLE ROW LEVEL SECURITY;

--
-- Name: users; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

--
-- Name: village_entry_photos; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.village_entry_photos ENABLE ROW LEVEL SECURITY;

--
-- Name: village_households; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.village_households ENABLE ROW LEVEL SECURITY;

--
-- Name: village_id_photos; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.village_id_photos ENABLE ROW LEVEL SECURITY;

--
-- Name: village_lots; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.village_lots ENABLE ROW LEVEL SECURITY;

--
-- Name: village_maps; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.village_maps ENABLE ROW LEVEL SECURITY;

--
-- Name: village_members; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.village_members ENABLE ROW LEVEL SECURITY;

--
-- Name: village_vehicle_checks; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.village_vehicle_checks ENABLE ROW LEVEL SECURITY;

--
-- Name: village_visit_details; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.village_visit_details ENABLE ROW LEVEL SECURITY;

--
-- Name: village_visit_people; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.village_visit_people ENABLE ROW LEVEL SECURITY;

--
-- Name: visits; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.visits ENABLE ROW LEVEL SECURITY;

--
-- Name: vista_owned_tables; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.vista_owned_tables ENABLE ROW LEVEL SECURITY;

--
-- Name: vista_schema_migrations; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.vista_schema_migrations ENABLE ROW LEVEL SECURITY;


--
-- Removes the demo village (and, through the foreign keys, its accounts, households, visits, photos, alerts and audit rows).
-- Leaves the tables and the migration records, so the database is then the same as a brand-new empty one.
--

CREATE FUNCTION public.vista_remove_demo() RETURNS text
    LANGUAGE plpgsql
    AS $$
DECLARE n integer;
BEGIN
  DELETE FROM public.properties WHERE slug = 'greenfield-village-7f3a';
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n = 0 THEN
    RETURN 'Walang demo village na mabubura (wala na ito, o ibang village ang gamit mo).';
  END IF;
  RETURN 'Nabura ang demo village at lahat ng nakakabit dito. Handa na ang database para sa sarili mong village.';
END;
$$;

--
-- PostgreSQL database dump complete
--

