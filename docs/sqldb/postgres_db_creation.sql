/*
================================================================================
  ChartNexus — PostgreSQL schema reference
================================================================================

  GENERATED, NOT HAND-WRITTEN. A schema-only `pg_dump` of a development
  database at Alembic head b7c4e1d9a2f6 (2026-11-18, after the Kite broker
  migration), checked with `alembic check` to have no model drift.

  This file is for READING — to see every table, column, constraint and index
  in one place. It is NOT how a database is created:

      cd backend && uv run alembic upgrade head

  Alembic (backend/migrations/versions/<context>/) is the only source of truth.
  Loading this file instead would leave `alembic_version` empty, and the next
  `upgrade head` would try to create every table again.

  Requirements it reflects: PostgreSQL 18 (uses the built-in uuidv7()).
  Connection: CN_DB_URL in backend/.env
              (local: postgresql+asyncpg://chartnexus:chartnexus@localhost:5433/chartnexus)

  Regenerate after a migration:

      docker exec chartnexus-postgres-1 pg_dump -U chartnexus -d chartnexus \
        --schema-only --no-owner --no-privileges --exclude-table=alembic_version

  then keep this header and update the head revision above.

  This replaces an earlier hand-written design script (the "Strikfin" draft)
  that described tables the application never built; it is in git history.
================================================================================
*/

--
-- PostgreSQL database dump
--

\restrict PwOERZgeJnqLYt94qebEowd9OC1SYMEudvopRfbzqFbV8XYtBJyu98ha1UU1Vit

-- Dumped from database version 18.4
-- Dumped by pg_dump version 18.4

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: broker_connections; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.broker_connections (
    tenant_id uuid NOT NULL,
    broker character varying(32) NOT NULL,
    app_id character varying(64),
    app_secret_enc text,
    access_token_enc text,
    refresh_token_enc text,
    status character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    profile jsonb,
    connected_at timestamp with time zone,
    revoked_at timestamp with time zone,
    expires_at timestamp with time zone,
    last_validated_at timestamp with time zone,
    last_error character varying(255),
    id uuid DEFAULT uuidv7() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    client_id character varying(16),
    CONSTRAINT ck_broker_connections_active_requires_token CHECK ((((status)::text <> 'active'::text) OR (access_token_enc IS NOT NULL))),
    CONSTRAINT ck_broker_connections_broker_known CHECK (((broker)::text = ANY ((ARRAY['fyers'::character varying, 'kite'::character varying])::text[]))),
    CONSTRAINT ck_broker_connections_status_known CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'active'::character varying, 'expired'::character varying, 'revoked'::character varying])::text[])))
);


--
-- Name: channel_connections; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.channel_connections (
    user_id uuid NOT NULL,
    channel character varying(32) NOT NULL,
    secret_enc text,
    target character varying(64),
    label character varying(128),
    verified boolean DEFAULT false NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    tenant_id uuid NOT NULL,
    id uuid DEFAULT uuidv7() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_channel_connections_channel_known CHECK (((channel)::text = ANY ((ARRAY['telegram'::character varying, 'whatsapp'::character varying])::text[])))
);


--
-- Name: daily_iv_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.daily_iv_history (
    symbol character varying(20) NOT NULL,
    session_date date NOT NULL,
    atm_iv numeric(7,3) NOT NULL,
    future_close numeric(12,2),
    captures integer NOT NULL,
    source character varying(8) NOT NULL,
    id uuid DEFAULT uuidv7() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_daily_iv_history_atm_iv_positive CHECK ((atm_iv > (0)::numeric)),
    CONSTRAINT ck_daily_iv_history_captures_positive CHECK ((captures > 0)),
    CONSTRAINT ck_daily_iv_history_source_known CHECK (((source)::text = ANY ((ARRAY['live'::character varying, 'mock'::character varying])::text[])))
);


--
-- Name: federated_identities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.federated_identities (
    user_id uuid NOT NULL,
    provider character varying(32) NOT NULL,
    subject character varying(255) NOT NULL,
    email character varying(254) NOT NULL,
    id uuid DEFAULT uuidv7() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_federated_identities_provider_known CHECK (((provider)::text = ANY ((ARRAY['password'::character varying, 'google'::character varying])::text[])))
);


--
-- Name: futures_board_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.futures_board_snapshots (
    symbol character varying(20) NOT NULL,
    session_date date NOT NULL,
    captured_at timestamp with time zone NOT NULL,
    price numeric(14,2) NOT NULL,
    open_interest bigint,
    volume bigint,
    expiry character varying(10),
    source character varying(8) NOT NULL,
    id uuid DEFAULT uuidv7() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_futures_board_snapshots_open_interest_not_negative CHECK (((open_interest IS NULL) OR (open_interest >= 0))),
    CONSTRAINT ck_futures_board_snapshots_price_positive CHECK ((price > (0)::numeric)),
    CONSTRAINT ck_futures_board_snapshots_source_known CHECK (((source)::text = ANY ((ARRAY['live'::character varying, 'mock'::character varying])::text[])))
);


--
-- Name: hugin_calls; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hugin_calls (
    tenant_id uuid NOT NULL,
    instrument character varying(64) NOT NULL,
    bias character varying(16) NOT NULL,
    target_zone text NOT NULL,
    conviction numeric NOT NULL,
    track_hit_rate numeric,
    rationale text NOT NULL,
    entry character varying(64),
    stop character varying(64),
    target1 character varying(64),
    target2 character varying(64),
    grade character varying(8),
    score numeric,
    id uuid DEFAULT uuidv7() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_hugin_calls_bias_known CHECK (((bias)::text = ANY ((ARRAY['BULLISH'::character varying, 'BEARISH'::character varying, 'NEUTRAL'::character varying])::text[])))
);


--
-- Name: hugin_enrollment; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hugin_enrollment (
    tenant_id uuid NOT NULL,
    enabled boolean DEFAULT false NOT NULL,
    id uuid DEFAULT uuidv7() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: hugin_lessons; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hugin_lessons (
    tenant_id uuid NOT NULL,
    instrument character varying(64),
    dedup_key character varying(128) NOT NULL,
    text text NOT NULL,
    hits integer DEFAULT 0 NOT NULL,
    misses integer DEFAULT 0 NOT NULL,
    last_seen_at timestamp with time zone,
    id uuid DEFAULT uuidv7() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: hugin_observations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hugin_observations (
    tenant_id uuid NOT NULL,
    instrument character varying(64) NOT NULL,
    tick_at timestamp with time zone NOT NULL,
    trading_day date NOT NULL,
    readings jsonb NOT NULL,
    bias character varying(16) NOT NULL,
    expectation text NOT NULL,
    call_wall numeric,
    put_wall numeric,
    key_level numeric,
    grade character varying(8),
    score numeric,
    grade_evidence jsonb,
    id uuid DEFAULT uuidv7() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_hugin_observations_bias_known CHECK (((bias)::text = ANY ((ARRAY['BULLISH'::character varying, 'BEARISH'::character varying, 'NEUTRAL'::character varying])::text[]))),
    CONSTRAINT ck_hugin_observations_grade_known CHECK (((grade IS NULL) OR ((grade)::text = ANY ((ARRAY['HIT'::character varying, 'PARTIAL'::character varying, 'MISS'::character varying])::text[]))))
);


--
-- Name: instruments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.instruments (
    symbol character varying(20) NOT NULL,
    kind character varying(8) NOT NULL,
    name character varying(128) NOT NULL,
    exchange character varying(8) NOT NULL,
    lot_size integer NOT NULL,
    tick_size numeric(12,4) NOT NULL,
    strike_step numeric(12,4),
    spot_symbol character varying(64) NOT NULL,
    futures_root character varying(32) NOT NULL,
    isin character varying(12),
    underlying_token character varying(32),
    sector character varying(64),
    is_active boolean DEFAULT true NOT NULL,
    id uuid DEFAULT uuidv7() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    reference_price numeric(18,4),
    indices character varying(128),
    front_expiry date,
    futures_expiries character varying(128),
    CONSTRAINT ck_instruments_instrument_kind_known CHECK (((kind)::text = ANY ((ARRAY['index'::character varying, 'stock'::character varying])::text[]))),
    CONSTRAINT ck_instruments_instrument_lot_size_positive CHECK ((lot_size > 0))
);


--
-- Name: kite_instruments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.kite_instruments (
    instrument_token bigint NOT NULL,
    exchange character varying(8) NOT NULL,
    segment character varying(16) NOT NULL,
    tradingsymbol character varying(64) NOT NULL,
    name character varying(128) DEFAULT ''::character varying NOT NULL,
    instrument_type character varying(8) NOT NULL,
    expiry date,
    strike numeric(14,4),
    lot_size integer DEFAULT 1 NOT NULL,
    tick_size numeric(10,4) DEFAULT 0.05 NOT NULL,
    synced_at timestamp with time zone NOT NULL
);


--
-- Name: kite_instruments_instrument_token_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.kite_instruments_instrument_token_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: kite_instruments_instrument_token_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.kite_instruments_instrument_token_seq OWNED BY public.kite_instruments.instrument_token;


--
-- Name: mme100_briefings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mme100_briefings (
    tenant_id uuid NOT NULL,
    trading_day date NOT NULL,
    instruments character varying(64)[] NOT NULL,
    markdown text NOT NULL,
    source character varying(8) NOT NULL,
    id uuid DEFAULT uuidv7() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mme100_enrollment; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mme100_enrollment (
    tenant_id uuid NOT NULL,
    enabled boolean DEFAULT false NOT NULL,
    id uuid DEFAULT uuidv7() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: option_chain_rows; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.option_chain_rows (
    snapshot_id uuid NOT NULL,
    strike numeric(12,2) NOT NULL,
    option_type character varying(2) NOT NULL,
    oi bigint NOT NULL,
    oi_change bigint NOT NULL,
    volume bigint NOT NULL,
    ltp numeric(12,2),
    iv numeric(7,3),
    delta numeric(7,4),
    id uuid DEFAULT uuidv7() NOT NULL,
    CONSTRAINT ck_option_chain_rows_option_type_known CHECK (((option_type)::text = ANY ((ARRAY['CE'::character varying, 'PE'::character varying])::text[]))),
    CONSTRAINT ck_option_chain_rows_strike_positive CHECK ((strike > (0)::numeric))
);


--
-- Name: option_chain_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.option_chain_snapshots (
    symbol character varying(20) NOT NULL,
    session_date date NOT NULL,
    captured_at timestamp with time zone NOT NULL,
    expiry character varying(10),
    spot numeric(12,2) NOT NULL,
    future_price numeric(12,2),
    lot_size integer,
    atm_strike numeric(12,2),
    total_call_oi bigint,
    total_put_oi bigint,
    pcr_oi numeric(8,4),
    max_pain_strike numeric(12,2),
    source character varying(8) NOT NULL,
    id uuid DEFAULT uuidv7() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_option_chain_snapshots_source_known CHECK (((source)::text = ANY ((ARRAY['live'::character varying, 'mock'::character varying])::text[]))),
    CONSTRAINT ck_option_chain_snapshots_spot_positive CHECK ((spot > (0)::numeric))
);


--
-- Name: price_candles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.price_candles (
    symbol character varying(20) NOT NULL,
    "interval" character varying(4) NOT NULL,
    bucket_start timestamp with time zone NOT NULL,
    open numeric(12,2) NOT NULL,
    high numeric(12,2) NOT NULL,
    low numeric(12,2) NOT NULL,
    close numeric(12,2) NOT NULL,
    volume bigint NOT NULL,
    source character varying(8) NOT NULL,
    id uuid DEFAULT uuidv7() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: refresh_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.refresh_sessions (
    family_id uuid NOT NULL,
    user_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    token_hash character varying(64) NOT NULL,
    issued_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    used_at timestamp with time zone,
    revoked_at timestamp with time zone,
    revocation_reason character varying(32),
    replaced_by_id uuid,
    generation integer DEFAULT 0 NOT NULL,
    user_agent character varying(400),
    ip_address character varying(45),
    id uuid DEFAULT uuidv7() NOT NULL,
    CONSTRAINT ck_refresh_sessions_expires_after_issue CHECK ((expires_at > issued_at)),
    CONSTRAINT ck_refresh_sessions_generation_non_negative CHECK ((generation >= 0))
);


--
-- Name: report_enrollment; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.report_enrollment (
    tenant_id uuid NOT NULL,
    enabled boolean DEFAULT false NOT NULL,
    id uuid DEFAULT uuidv7() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: signal_decisions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.signal_decisions (
    tenant_id uuid NOT NULL,
    symbol character varying(20) NOT NULL,
    generated_at timestamp with time zone NOT NULL,
    decision character varying(4) NOT NULL,
    confidence integer NOT NULL,
    score numeric(6,4) NOT NULL,
    components jsonb NOT NULL,
    entry numeric(12,2),
    stop numeric(12,2),
    target numeric(12,2),
    risk_reward numeric(6,2),
    suggested_contract character varying(64),
    provenance_source character varying(8) NOT NULL,
    expiry_ref character varying(10),
    is_actionable boolean NOT NULL,
    id uuid DEFAULT uuidv7() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_signal_decisions_confidence_range CHECK (((confidence >= 0) AND (confidence <= 100))),
    CONSTRAINT ck_signal_decisions_decision_known CHECK (((decision)::text = ANY ((ARRAY['BUY'::character varying, 'SELL'::character varying, 'HOLD'::character varying])::text[]))),
    CONSTRAINT ck_signal_decisions_provenance_known CHECK (((provenance_source)::text = ANY ((ARRAY['live'::character varying, 'cached'::character varying, 'mock'::character varying])::text[])))
);


--
-- Name: stryx_calls; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.stryx_calls (
    tenant_id uuid NOT NULL,
    question text NOT NULL,
    status character varying(10) NOT NULL,
    instrument character varying(64),
    entry_style character varying(32),
    entry character varying(64),
    stop character varying(64),
    target1 character varying(64),
    target2 character varying(64),
    confidence character varying(16),
    reasoning text,
    raw_answer text NOT NULL,
    source character varying(8) NOT NULL,
    id uuid DEFAULT uuidv7() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_stryx_calls_source_known CHECK (((source)::text = ANY ((ARRAY['live'::character varying, 'mock'::character varying])::text[]))),
    CONSTRAINT ck_stryx_calls_status_known CHECK (((status)::text = ANY ((ARRAY['LIVE'::character varying, 'NO_TRADE'::character varying, 'WATCHING'::character varying])::text[])))
);


--
-- Name: trade_buddy_channels; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.trade_buddy_channels (
    user_id uuid NOT NULL,
    channel character varying(32) NOT NULL,
    secret_enc text,
    target character varying(64),
    label character varying(128),
    verified boolean DEFAULT false NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    tenant_id uuid NOT NULL,
    id uuid DEFAULT uuidv7() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_trade_buddy_channels_ck_trade_buddy_channels_trade_b_f305 CHECK (((channel)::text = ANY ((ARRAY['telegram'::character varying, 'whatsapp'::character varying])::text[])))
);


--
-- Name: user_ai_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_ai_settings (
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL,
    provider character varying(32) NOT NULL,
    model character varying(128) NOT NULL,
    api_key_enc text,
    id uuid DEFAULT uuidv7() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_user_ai_settings_ai_provider_known CHECK (((provider)::text = ANY ((ARRAY['anthropic'::character varying, 'openai'::character varying, 'openrouter'::character varying])::text[])))
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    tenant_id uuid NOT NULL,
    email character varying(254) NOT NULL,
    display_name character varying(120) NOT NULL,
    status character varying(32) DEFAULT 'active'::character varying NOT NULL,
    password_hash character varying(255),
    roles character varying(32)[] DEFAULT ARRAY['owner'::character varying] NOT NULL,
    email_verified_at timestamp with time zone,
    last_login_at timestamp with time zone,
    failed_login_count integer DEFAULT 0 NOT NULL,
    id uuid DEFAULT uuidv7() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    phone character varying(16),
    phone_verified_at timestamp with time zone,
    CONSTRAINT ck_users_failed_login_count_non_negative CHECK ((failed_login_count >= 0)),
    CONSTRAINT ck_users_phone_e164_india CHECK (((phone IS NULL) OR ((phone)::text ~ '^\+91[6-9][0-9]{9}$'::text))),
    CONSTRAINT ck_users_status_known CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'pending_verification'::character varying, 'suspended'::character varying, 'deactivated'::character varying])::text[])))
);


--
-- Name: kite_instruments instrument_token; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kite_instruments ALTER COLUMN instrument_token SET DEFAULT nextval('public.kite_instruments_instrument_token_seq'::regclass);


--
-- Name: futures_board_snapshots futures_board_snapshots_symbol_instant; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.futures_board_snapshots
    ADD CONSTRAINT futures_board_snapshots_symbol_instant UNIQUE (symbol, captured_at);


--
-- Name: broker_connections pk_broker_connections; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broker_connections
    ADD CONSTRAINT pk_broker_connections PRIMARY KEY (id);


--
-- Name: channel_connections pk_channel_connections; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.channel_connections
    ADD CONSTRAINT pk_channel_connections PRIMARY KEY (id);


--
-- Name: daily_iv_history pk_daily_iv_history; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_iv_history
    ADD CONSTRAINT pk_daily_iv_history PRIMARY KEY (id);


--
-- Name: federated_identities pk_federated_identities; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.federated_identities
    ADD CONSTRAINT pk_federated_identities PRIMARY KEY (id);


--
-- Name: futures_board_snapshots pk_futures_board_snapshots; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.futures_board_snapshots
    ADD CONSTRAINT pk_futures_board_snapshots PRIMARY KEY (id);


--
-- Name: hugin_calls pk_hugin_calls; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hugin_calls
    ADD CONSTRAINT pk_hugin_calls PRIMARY KEY (id);


--
-- Name: hugin_enrollment pk_hugin_enrollment; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hugin_enrollment
    ADD CONSTRAINT pk_hugin_enrollment PRIMARY KEY (id);


--
-- Name: hugin_lessons pk_hugin_lessons; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hugin_lessons
    ADD CONSTRAINT pk_hugin_lessons PRIMARY KEY (id);


--
-- Name: hugin_observations pk_hugin_observations; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hugin_observations
    ADD CONSTRAINT pk_hugin_observations PRIMARY KEY (id);


--
-- Name: instruments pk_instruments; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.instruments
    ADD CONSTRAINT pk_instruments PRIMARY KEY (id);


--
-- Name: kite_instruments pk_kite_instruments; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kite_instruments
    ADD CONSTRAINT pk_kite_instruments PRIMARY KEY (instrument_token);


--
-- Name: mme100_briefings pk_mme100_briefings; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mme100_briefings
    ADD CONSTRAINT pk_mme100_briefings PRIMARY KEY (id);


--
-- Name: mme100_enrollment pk_mme100_enrollment; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mme100_enrollment
    ADD CONSTRAINT pk_mme100_enrollment PRIMARY KEY (id);


--
-- Name: option_chain_rows pk_option_chain_rows; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.option_chain_rows
    ADD CONSTRAINT pk_option_chain_rows PRIMARY KEY (id);


--
-- Name: option_chain_snapshots pk_option_chain_snapshots; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.option_chain_snapshots
    ADD CONSTRAINT pk_option_chain_snapshots PRIMARY KEY (id);


--
-- Name: price_candles pk_price_candles; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.price_candles
    ADD CONSTRAINT pk_price_candles PRIMARY KEY (id);


--
-- Name: refresh_sessions pk_refresh_sessions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refresh_sessions
    ADD CONSTRAINT pk_refresh_sessions PRIMARY KEY (id);


--
-- Name: report_enrollment pk_report_enrollment; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_enrollment
    ADD CONSTRAINT pk_report_enrollment PRIMARY KEY (id);


--
-- Name: signal_decisions pk_signal_decisions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.signal_decisions
    ADD CONSTRAINT pk_signal_decisions PRIMARY KEY (id);


--
-- Name: stryx_calls pk_stryx_calls; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stryx_calls
    ADD CONSTRAINT pk_stryx_calls PRIMARY KEY (id);


--
-- Name: trade_buddy_channels pk_trade_buddy_channels; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trade_buddy_channels
    ADD CONSTRAINT pk_trade_buddy_channels PRIMARY KEY (id);


--
-- Name: user_ai_settings pk_user_ai_settings; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_ai_settings
    ADD CONSTRAINT pk_user_ai_settings PRIMARY KEY (id);


--
-- Name: users pk_users; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT pk_users PRIMARY KEY (id);


--
-- Name: daily_iv_history uq_daily_iv_history_session; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_iv_history
    ADD CONSTRAINT uq_daily_iv_history_session UNIQUE (symbol, session_date);


--
-- Name: federated_identities uq_federated_identities_provider_subject; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.federated_identities
    ADD CONSTRAINT uq_federated_identities_provider_subject UNIQUE (provider, subject);


--
-- Name: federated_identities uq_federated_identities_user_id_provider; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.federated_identities
    ADD CONSTRAINT uq_federated_identities_user_id_provider UNIQUE (user_id, provider);


--
-- Name: hugin_enrollment uq_hugin_enrollment_tenant; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hugin_enrollment
    ADD CONSTRAINT uq_hugin_enrollment_tenant UNIQUE (tenant_id);


--
-- Name: hugin_lessons uq_hugin_lessons_dedup; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hugin_lessons
    ADD CONSTRAINT uq_hugin_lessons_dedup UNIQUE (tenant_id, dedup_key);


--
-- Name: mme100_briefings uq_mme100_briefing_tenant_day; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mme100_briefings
    ADD CONSTRAINT uq_mme100_briefing_tenant_day UNIQUE (tenant_id, trading_day);


--
-- Name: mme100_enrollment uq_mme100_enrollment_tenant; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mme100_enrollment
    ADD CONSTRAINT uq_mme100_enrollment_tenant UNIQUE (tenant_id);


--
-- Name: price_candles uq_price_candles_bar; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.price_candles
    ADD CONSTRAINT uq_price_candles_bar UNIQUE (symbol, "interval", bucket_start);


--
-- Name: refresh_sessions uq_refresh_sessions_token_hash; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refresh_sessions
    ADD CONSTRAINT uq_refresh_sessions_token_hash UNIQUE (token_hash);


--
-- Name: report_enrollment uq_report_enrollment_tenant; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.report_enrollment
    ADD CONSTRAINT uq_report_enrollment_tenant UNIQUE (tenant_id);


--
-- Name: users uq_users_email; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT uq_users_email UNIQUE (email);


--
-- Name: users uq_users_phone; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT uq_users_phone UNIQUE (phone);


--
-- Name: ix_broker_connections_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_broker_connections_tenant_id ON public.broker_connections USING btree (tenant_id);


--
-- Name: ix_channel_connections_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_channel_connections_tenant_id ON public.channel_connections USING btree (tenant_id);


--
-- Name: ix_daily_iv_history_lookup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_daily_iv_history_lookup ON public.daily_iv_history USING btree (symbol, session_date);


--
-- Name: ix_federated_identities_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_federated_identities_email ON public.federated_identities USING btree (email);


--
-- Name: ix_futures_board_snapshots_lookup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_futures_board_snapshots_lookup ON public.futures_board_snapshots USING btree (symbol, session_date, captured_at);


--
-- Name: ix_hugin_calls_lookup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_hugin_calls_lookup ON public.hugin_calls USING btree (tenant_id, instrument, created_at);


--
-- Name: ix_hugin_calls_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_hugin_calls_tenant_id ON public.hugin_calls USING btree (tenant_id);


--
-- Name: ix_hugin_enrollment_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_hugin_enrollment_tenant_id ON public.hugin_enrollment USING btree (tenant_id);


--
-- Name: ix_hugin_lessons_lookup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_hugin_lessons_lookup ON public.hugin_lessons USING btree (tenant_id, instrument);


--
-- Name: ix_hugin_lessons_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_hugin_lessons_tenant_id ON public.hugin_lessons USING btree (tenant_id);


--
-- Name: ix_hugin_observations_lookup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_hugin_observations_lookup ON public.hugin_observations USING btree (tenant_id, instrument, tick_at);


--
-- Name: ix_hugin_observations_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_hugin_observations_tenant_id ON public.hugin_observations USING btree (tenant_id);


--
-- Name: ix_instruments_active_kind; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instruments_active_kind ON public.instruments USING btree (is_active, kind);


--
-- Name: ix_kite_instruments_exchange_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kite_instruments_exchange_symbol ON public.kite_instruments USING btree (exchange, tradingsymbol);


--
-- Name: ix_kite_instruments_name_segment_expiry; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kite_instruments_name_segment_expiry ON public.kite_instruments USING btree (name, segment, expiry);


--
-- Name: ix_kite_instruments_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kite_instruments_type ON public.kite_instruments USING btree (instrument_type);


--
-- Name: ix_mme100_briefings_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mme100_briefings_tenant_id ON public.mme100_briefings USING btree (tenant_id);


--
-- Name: ix_mme100_enrollment_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mme100_enrollment_tenant_id ON public.mme100_enrollment USING btree (tenant_id);


--
-- Name: ix_option_chain_rows_snapshot; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_option_chain_rows_snapshot ON public.option_chain_rows USING btree (snapshot_id, option_type, strike);


--
-- Name: ix_option_chain_snapshots_lookup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_option_chain_snapshots_lookup ON public.option_chain_snapshots USING btree (symbol, session_date, captured_at);


--
-- Name: ix_price_candles_lookup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_price_candles_lookup ON public.price_candles USING btree (symbol, "interval", bucket_start);


--
-- Name: ix_refresh_sessions_expires_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_refresh_sessions_expires_at ON public.refresh_sessions USING btree (expires_at);


--
-- Name: ix_refresh_sessions_family_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_refresh_sessions_family_id ON public.refresh_sessions USING btree (family_id);


--
-- Name: ix_refresh_sessions_user_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_refresh_sessions_user_active ON public.refresh_sessions USING btree (user_id, expires_at) WHERE ((revoked_at IS NULL) AND (used_at IS NULL));


--
-- Name: ix_report_enrollment_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_report_enrollment_tenant_id ON public.report_enrollment USING btree (tenant_id);


--
-- Name: ix_signal_decisions_lookup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_signal_decisions_lookup ON public.signal_decisions USING btree (tenant_id, symbol, generated_at);


--
-- Name: ix_signal_decisions_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_signal_decisions_tenant_id ON public.signal_decisions USING btree (tenant_id);


--
-- Name: ix_stryx_calls_lookup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_stryx_calls_lookup ON public.stryx_calls USING btree (tenant_id, created_at);


--
-- Name: ix_stryx_calls_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_stryx_calls_tenant_id ON public.stryx_calls USING btree (tenant_id);


--
-- Name: ix_trade_buddy_channels_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_trade_buddy_channels_tenant_id ON public.trade_buddy_channels USING btree (tenant_id);


--
-- Name: ix_user_ai_settings_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_ai_settings_tenant_id ON public.user_ai_settings USING btree (tenant_id);


--
-- Name: ix_users_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_users_tenant_id ON public.users USING btree (tenant_id);


--
-- Name: uq_broker_connections_one_active; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_broker_connections_one_active ON public.broker_connections USING btree (tenant_id) WHERE ((status)::text = 'active'::text);


--
-- Name: uq_broker_connections_tenant_broker; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_broker_connections_tenant_broker ON public.broker_connections USING btree (tenant_id, broker);


--
-- Name: uq_channel_connections_user_channel; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_channel_connections_user_channel ON public.channel_connections USING btree (user_id, channel);


--
-- Name: uq_instruments_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_instruments_symbol ON public.instruments USING btree (symbol);


--
-- Name: uq_trade_buddy_channels_user_channel; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_trade_buddy_channels_user_channel ON public.trade_buddy_channels USING btree (user_id, channel);


--
-- Name: uq_user_ai_settings_user; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_user_ai_settings_user ON public.user_ai_settings USING btree (user_id);


--
-- Name: federated_identities fk_federated_identities_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.federated_identities
    ADD CONSTRAINT fk_federated_identities_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: option_chain_rows fk_option_chain_rows_snapshot_id_option_chain_snapshots; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.option_chain_rows
    ADD CONSTRAINT fk_option_chain_rows_snapshot_id_option_chain_snapshots FOREIGN KEY (snapshot_id) REFERENCES public.option_chain_snapshots(id) ON DELETE CASCADE;


--
-- Name: refresh_sessions fk_refresh_sessions_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refresh_sessions
    ADD CONSTRAINT fk_refresh_sessions_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict PwOERZgeJnqLYt94qebEowd9OC1SYMEudvopRfbzqFbV8XYtBJyu98ha1UU1Vit

