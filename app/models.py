from __future__ import annotations
import time
from sqlalchemy import Column, String, Text, BigInteger, Integer, LargeBinary, Boolean, Numeric, UniqueConstraint, CheckConstraint, Index
from .db import Base

def _now_ts():
    """Return current epoch seconds as int. Used as ORM column default."""
    return int(time.time())

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    email = Column(String, index=True, nullable=False)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False, default="user")  # user|admin
    salt = Column(String, nullable=False)
    pw_hash = Column(String, nullable=False)
    created_at = Column(BigInteger, nullable=False)
    approved_at = Column(BigInteger, nullable=True)
    # PATCH0100_28: Summit fields
    signup_code_label = Column(String, nullable=True)
    signup_source = Column(String, nullable=True)       # pitch | invite
    usage_tier = Column(String, nullable=True, default="summit_standard")  # summit_standard | summit_vip
    terms_accepted_at = Column(BigInteger, nullable=True)
    terms_version = Column(String, nullable=True)
    marketing_consent = Column(Boolean, nullable=True, default=False)
    # PATCH v3.3.1a — strategic onboarding profile
    company = Column(String, nullable=True)
    profile_role = Column(String, nullable=True)
    user_type = Column(String, nullable=True)
    intent = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    country = Column(String, nullable=True)
    language = Column(String, nullable=True)
    whatsapp = Column(String, nullable=True)
    onboarding_completed = Column(Boolean, nullable=False, default=False)

class Thread(Base):
    __tablename__ = "threads"
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    title = Column(String, nullable=False)
    created_at = Column(BigInteger, nullable=False)

class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_org_thread", "org_slug", "thread_id"),
        Index("ux_messages_org_thread_client_msg", "org_slug", "thread_id", "client_message_id", unique=True),
    )
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    thread_id = Column(String, index=True, nullable=False)
    user_id = Column(String, nullable=True)
    user_name = Column(String, nullable=True)
    role = Column(String, nullable=False)  # user|assistant|system
    content = Column(Text, nullable=False)
    agent_id = Column(String, nullable=True)
    agent_name = Column(String, nullable=True)
    client_message_id = Column(String, nullable=True)
    created_at = Column(BigInteger, nullable=False, default=_now_ts)

    def __init__(self, **kwargs):
        if "created_at" not in kwargs or kwargs["created_at"] is None:
            kwargs["created_at"] = _now_ts()
        super().__init__(**kwargs)

class File(Base):
    __tablename__ = "files"
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    thread_id = Column(String, index=True, nullable=True)
    uploader_id = Column(String, nullable=True)
    uploader_name = Column(String, nullable=True)
    uploader_email = Column(String, nullable=True)
    filename = Column(String, nullable=False)
    original_filename = Column(String, nullable=True)
    origin = Column(String, nullable=False, default='unknown')
    scope_thread_id = Column(String, nullable=True)
    scope_agent_id = Column(String, nullable=True)
    mime_type = Column(String, nullable=True)
    size_bytes = Column(Integer, nullable=False, default=0)
    content = Column(LargeBinary, nullable=True)
    extraction_failed = Column(Boolean, nullable=False, default=False)
    is_institutional = Column(Boolean, nullable=False, default=False)
    created_at = Column(BigInteger, nullable=False)

class FileText(Base):
    __tablename__ = "file_texts"
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    file_id = Column(String, index=True, nullable=False)
    text = Column(Text, nullable=False)
    extracted_chars = Column(Integer, nullable=False, default=0)
    created_at = Column(BigInteger, nullable=False)

class FileChunk(Base):
    __tablename__ = "file_chunks"
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    file_id = Column(String, index=True, nullable=False)
    idx = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    agent_id = Column(String, nullable=True)
    agent_name = Column(String, nullable=True)
    created_at = Column(BigInteger, nullable=False)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    user_id = Column(String, nullable=True)
    action = Column(String, nullable=False)
    meta = Column(Text, nullable=True)
    request_id = Column(String, nullable=True)
    path = Column(String, nullable=True)
    status_code = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(BigInteger, nullable=False)


class Agent(Base):
    __tablename__ = "agents"
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    system_prompt = Column(Text, nullable=False, default="")
    model = Column(String, nullable=True)
    embedding_model = Column(String, nullable=True)
    temperature = Column(String, nullable=True)
    rag_enabled = Column(Boolean, nullable=False, default=True)
    rag_top_k = Column(Integer, nullable=False, default=6)
    is_default = Column(Boolean, nullable=False, default=False)
    voice_id = Column(String, nullable=True, default="nova")
    avatar_url = Column(String, nullable=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

class AgentKnowledge(Base):
    __tablename__ = "agent_knowledge"
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    agent_id = Column(String, index=True, nullable=False)
    file_id = Column(String, index=True, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(BigInteger, nullable=False)


class AgentLink(Base):
    __tablename__ = "agent_links"
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    source_agent_id = Column(String, index=True, nullable=False)
    target_agent_id = Column(String, index=True, nullable=False)
    mode = Column(String, nullable=False, default="consult")
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(BigInteger, nullable=False)


class CostEvent(Base):
    __tablename__ = "cost_events"
    __table_args__ = (
        Index("ix_cost_events_org_created", "org_slug", "created_at"),
    )
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    user_id = Column(String, nullable=True)
    thread_id = Column(String, index=True, nullable=True)
    message_id = Column(String, index=True, nullable=True)
    agent_id = Column(String, index=True, nullable=True)
    provider = Column(String, nullable=True)
    model = Column(String, nullable=True, index=True)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    input_cost_usd = Column(Numeric(12, 6), nullable=False, default=0)
    output_cost_usd = Column(Numeric(12, 6), nullable=False, default=0)
    total_cost_usd = Column(Numeric(12, 6), nullable=False, default=0)
    cost_usd = Column(Numeric(12, 6), nullable=False, default=0)
    pricing_version = Column(String, nullable=False, default="2026-02-18")
    pricing_snapshot = Column(Text, nullable=True)
    usage_missing = Column(Boolean, nullable=False, default=False)
    meta = Column("metadata", Text, nullable=True)
    created_at = Column(BigInteger, nullable=False)


class FileRequest(Base):
    __tablename__ = "file_requests"
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    file_id = Column(String, index=True, nullable=False)
    requested_by_user_id = Column(String, nullable=True)
    requested_by_user_name = Column(String, nullable=True)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(BigInteger, nullable=False)
    resolved_at = Column(BigInteger, nullable=True)
    resolved_by_admin_id = Column(String, nullable=True)


class PricingSnapshot(Base):
    __tablename__ = "pricing_snapshots"
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False, default="public")
    provider = Column(String, index=True, nullable=False, default="openai")
    model = Column(String, index=True, nullable=False)
    input_per_1m = Column(Numeric(10, 6), nullable=False, default=0)
    output_per_1m = Column(Numeric(10, 6), nullable=False, default=0)
    currency = Column(String, nullable=False, default="USD")
    source = Column(String, nullable=True)
    fetched_at = Column(BigInteger, nullable=False)
    effective_at = Column(BigInteger, nullable=False)


class Lead(Base):
    __tablename__ = "leads"
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False, default="public")
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, index=True)
    company = Column(String, nullable=False)
    role = Column(String, nullable=True)
    segment = Column(String, nullable=True)
    source = Column(String, nullable=True, default="qr")
    ua = Column(String, nullable=True)
    created_at = Column(BigInteger, nullable=False)


class ThreadMember(Base):
    __tablename__ = "thread_members"
    __table_args__ = (
        UniqueConstraint("thread_id", "user_id", name="uq_thread_members_thread_user"),
        CheckConstraint("role IN ('owner','admin','member','viewer')", name="ck_thread_members_role"),
    )
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    thread_id = Column(String, index=True, nullable=False)
    user_id = Column(String, index=True, nullable=False)
    role = Column(String, nullable=False)
    created_at = Column(BigInteger, nullable=False)


class RealtimeSession(Base):
    __tablename__ = "realtime_sessions"
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    thread_id = Column(String, index=True, nullable=False)
    agent_id = Column(String, nullable=True)
    agent_name = Column(String, nullable=True)
    user_id = Column(String, nullable=True)
    user_name = Column(String, nullable=True)
    model = Column(String, nullable=True)
    voice = Column(String, nullable=True)
    started_at = Column(BigInteger, nullable=False)
    ended_at = Column(BigInteger, nullable=True)
    meta = Column(Text, nullable=True)

class RealtimeEvent(Base):
    __tablename__ = "realtime_events"
    __table_args__ = (
        Index(
            "ux_realtime_events_org_sess_client_eid",
            "org_slug",
            "session_id",
            "client_event_id",
            unique=True,
        ),
    )

    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)

    session_id = Column(String, index=True, nullable=False)
    thread_id = Column(String, index=True, nullable=False)

    # Schema-aligned fields (Railway production DB)
    speaker_type = Column(String, nullable=False)
    speaker_id = Column(String, nullable=True)

    agent_id = Column(String, nullable=True)
    agent_name = Column(String, nullable=True)

    event_type = Column(String, nullable=False)

    transcript_raw = Column(Text, nullable=True)
    transcript_punct = Column(Text, nullable=True)

    created_at = Column(BigInteger, nullable=False)

    client_event_id = Column(String, nullable=True)

    meta = Column(Text, nullable=True)


# ═══════════════════════════════════════════════════════════════════════
# PATCH0100_28 — Summit Hardening + Legal Compliance
# ═══════════════════════════════════════════════════════════════════════

class SignupCode(Base):
    __tablename__ = "signup_codes"
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    code_hash = Column(String, nullable=False)
    label = Column(String, nullable=False)
    source = Column(String, nullable=False)          # pitch | invite
    expires_at = Column(BigInteger, nullable=False)
    max_uses = Column(Integer, nullable=False, default=500)
    used_count = Column(Integer, nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(BigInteger, nullable=False)
    created_by = Column(String, nullable=True)

class OtpCode(Base):
    __tablename__ = "otp_codes"
    id = Column(String, primary_key=True)
    user_id = Column(String, index=True, nullable=False)
    code_hash = Column(String, nullable=False)
    expires_at = Column(BigInteger, nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    verified = Column(Boolean, nullable=False, default=False)
    created_at = Column(BigInteger, nullable=False)

class UserSession(Base):
    __tablename__ = "user_sessions"
    id = Column(String, primary_key=True)
    user_id = Column(String, index=True, nullable=False)
    org_slug = Column(String, index=True, nullable=False)
    login_at = Column(BigInteger, nullable=False)
    logout_at = Column(BigInteger, nullable=True)
    last_seen_at = Column(BigInteger, nullable=False)
    ended_reason = Column(String, nullable=True)     # logout | timeout | admin_kick
    duration_seconds = Column(Integer, nullable=True)
    source_code_label = Column(String, nullable=True)
    usage_tier = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)

class UsageEvent(Base):
    __tablename__ = "usage_events"
    id = Column(String, primary_key=True)
    user_id = Column(String, index=True, nullable=False)
    org_slug = Column(String, index=True, nullable=False)
    event_type = Column(String, nullable=False)      # chat | realtime | tts
    tokens_used = Column(Integer, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    created_at = Column(BigInteger, nullable=False)


class ValuationConfig(Base):
    __tablename__ = "valuation_configs"
    __table_args__ = (
        Index("ix_valuation_configs_org_unique", "org_slug", unique=True),
    )
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    paid_users_override = Column(Integer, nullable=True)
    individual_price_usd = Column(Numeric(12, 2), nullable=False, default=20)
    pro_price_usd = Column(Numeric(12, 2), nullable=False, default=49)
    team_base_price_usd = Column(Numeric(12, 2), nullable=False, default=99)
    team_seat_price_usd = Column(Numeric(12, 2), nullable=False, default=20)
    individual_share_pct = Column(Numeric(8, 2), nullable=False, default=50)
    pro_share_pct = Column(Numeric(8, 2), nullable=False, default=30)
    team_share_pct = Column(Numeric(8, 2), nullable=False, default=20)
    avg_team_size = Column(Numeric(8, 2), nullable=False, default=5)
    monthly_setup_revenue_usd = Column(Numeric(12, 2), nullable=False, default=0)
    monthly_enterprise_mrr_usd = Column(Numeric(12, 2), nullable=False, default=0)
    low_arr_multiple = Column(Numeric(8, 2), nullable=False, default=8)
    base_arr_multiple = Column(Numeric(8, 2), nullable=False, default=12)
    high_arr_multiple = Column(Numeric(8, 2), nullable=False, default=18)
    notes = Column(Text, nullable=True)
    updated_by = Column(String, nullable=True)
    updated_at = Column(BigInteger, nullable=False)



class BillingTransaction(Base):
    __tablename__ = "billing_transactions"
    __table_args__ = (
        Index("ix_billing_transactions_org_status_confirmed", "org_slug", "status", "confirmed_at"),
        Index("ix_billing_transactions_org_subscription", "org_slug", "subscription_key"),
    )
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    user_id = Column(String, nullable=True)
    payer_email = Column(String, nullable=True)
    payer_name = Column(String, nullable=True)
    provider = Column(String, nullable=False, default="manual")
    external_ref = Column(String, nullable=True)
    subscription_key = Column(String, nullable=True)
    plan_code = Column(String, nullable=True)
    charge_kind = Column(String, nullable=False, default="recurring")  # recurring|setup|enterprise|addon|refund
    currency = Column(String, nullable=False, default="USD")
    amount_original = Column(Numeric(12, 2), nullable=True)
    amount_usd = Column(Numeric(12, 2), nullable=False, default=0)
    normalized_mrr_usd = Column(Numeric(12, 2), nullable=True)
    status = Column(String, nullable=False, default="confirmed")  # pending|confirmed|refunded|void
    occurred_at = Column(BigInteger, nullable=True)
    confirmed_at = Column(BigInteger, nullable=True)
    notes = Column(Text, nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(BigInteger, nullable=False)



class BillingCheckout(Base):
    __tablename__ = "billing_checkouts"
    __table_args__ = (
        Index("ix_billing_checkouts_org_email", "org_slug", "email"),
        Index("ix_billing_checkouts_provider_checkout", "provider", "provider_checkout_id"),
    )
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    email = Column(String, index=True, nullable=False)
    full_name = Column(String, nullable=True)
    company = Column(String, nullable=True)
    plan_code = Column(String, nullable=False)
    plan_name = Column(String, nullable=False)
    amount_brl = Column(Numeric(12, 2), nullable=False, default=0)
    currency = Column(String, nullable=False, default="BRL")
    status = Column(String, nullable=False, default="pending")  # pending|paid|failed|expired|cancelled
    access_source = Column(String, nullable=False, default="payment")
    provider = Column(String, nullable=False, default="asaas")
    provider_checkout_id = Column(String, nullable=True)
    provider_payment_id = Column(String, nullable=True)
    provider_url = Column(String, nullable=True)
    callback_success_url = Column(String, nullable=True)
    meta = Column("metadata", Text, nullable=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)
    confirmed_at = Column(BigInteger, nullable=True)


class BillingWebhookEvent(Base):
    __tablename__ = "billing_webhook_events"
    __table_args__ = (
        Index("ix_billing_webhooks_provider_event", "provider", "provider_event_key", unique=True),
    )
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=True)
    provider = Column(String, nullable=False, default="asaas")
    provider_event_key = Column(String, nullable=False)
    event_type = Column(String, nullable=False)
    payload = Column(Text, nullable=True)
    processed = Column(Boolean, nullable=False, default=False)
    processed_at = Column(BigInteger, nullable=True)
    created_at = Column(BigInteger, nullable=False)


class BillingEntitlement(Base):
    __tablename__ = "billing_entitlements"
    __table_args__ = (
        Index("ix_billing_entitlements_org_email", "org_slug", "email", unique=True),
    )
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    email = Column(String, index=True, nullable=False)
    full_name = Column(String, nullable=True)
    plan_code = Column(String, nullable=False)
    plan_name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active")  # active|comped|expired|cancelled
    access_source = Column(String, nullable=False, default="payment")
    checkout_id = Column(String, nullable=True)
    provider_customer_id = Column(String, nullable=True)
    provider_subscription_id = Column(String, nullable=True)
    starts_at = Column(BigInteger, nullable=True)
    expires_at = Column(BigInteger, nullable=True)
    last_payment_at = Column(BigInteger, nullable=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)



class BillingWallet(Base):
    __tablename__ = "billing_wallets"
    __table_args__ = (
        Index("ix_billing_wallets_org_email", "org_slug", "email", unique=True),
    )
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    user_id = Column(String, nullable=True)
    email = Column(String, index=True, nullable=False)
    full_name = Column(String, nullable=True)
    currency = Column(String, nullable=False, default="USD")
    balance_usd = Column(Numeric(12, 4), nullable=False, default=0)
    lifetime_credited_usd = Column(Numeric(12, 4), nullable=False, default=0)
    lifetime_debited_usd = Column(Numeric(12, 4), nullable=False, default=0)
    auto_recharge_enabled = Column(Boolean, nullable=False, default=False)
    auto_recharge_pack_code = Column(String, nullable=True)
    auto_recharge_threshold_usd = Column(Numeric(12, 4), nullable=True)
    low_balance_threshold_usd = Column(Numeric(12, 4), nullable=True, default=3)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)


class BillingWalletLedger(Base):
    __tablename__ = "billing_wallet_ledger"
    __table_args__ = (
        Index("ix_billing_wallet_ledger_wallet_created", "wallet_id", "created_at"),
        Index("ix_billing_wallet_ledger_org_email_created", "org_slug", "email", "created_at"),
        Index("ix_billing_wallet_ledger_external_ref", "org_slug", "external_ref"),
    )
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    wallet_id = Column(String, index=True, nullable=False)
    user_id = Column(String, nullable=True)
    email = Column(String, index=True, nullable=False)
    direction = Column(String, nullable=False, default="credit")  # credit|debit|adjustment
    source = Column(String, nullable=False, default="manual")  # plan_included|topup|usage|refund|admin_adjustment
    action_key = Column(String, nullable=True)
    quantity = Column(Numeric(12, 4), nullable=True)
    unit_price_usd = Column(Numeric(12, 4), nullable=True)
    amount_usd = Column(Numeric(12, 4), nullable=False, default=0)
    balance_after_usd = Column(Numeric(12, 4), nullable=False, default=0)
    currency = Column(String, nullable=False, default="USD")
    provider = Column(String, nullable=True)
    external_ref = Column(String, nullable=True)
    related_checkout_id = Column(String, nullable=True)
    related_tx_id = Column(String, nullable=True)
    metadata = Column(Text, nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(BigInteger, nullable=False)

class FeatureFlag(Base):
    __tablename__ = "feature_flags"
    __table_args__ = (
        Index("ix_feature_flags_org_key", "org_slug", "flag_key", unique=True),
    )
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    flag_key = Column(String, nullable=False)
    flag_value = Column(String, nullable=False, default="true")
    updated_by = Column(String, nullable=True)
    updated_at = Column(BigInteger, nullable=False)

class ContactRequest(Base):
    __tablename__ = "contact_requests"
    id = Column(String, primary_key=True)
    full_name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    whatsapp = Column(String, nullable=True)
    subject = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    privacy_request_type = Column(String, nullable=True)
    consent_terms = Column(Boolean, nullable=False)
    consent_marketing = Column(Boolean, nullable=False, default=False)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    terms_version = Column(String, nullable=True)
    status = Column(String, nullable=False, default="pending")
    retention_until = Column(BigInteger, nullable=True)
    created_at = Column(BigInteger, nullable=False)

class MarketingConsent(Base):
    __tablename__ = "marketing_consents"
    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=True)
    contact_id = Column(String, nullable=True)
    channel = Column(String, nullable=False)         # email | whatsapp
    opt_in_date = Column(BigInteger, nullable=True)
    opt_out_date = Column(BigInteger, nullable=True)
    ip = Column(String, nullable=True)
    source = Column(String, nullable=True)
    created_at = Column(BigInteger, nullable=False)

class TermsAcceptance(Base):
    __tablename__ = "terms_acceptances"
    id = Column(String, primary_key=True)
    user_id = Column(String, index=True, nullable=False)
    terms_version = Column(String, nullable=False)
    accepted_at = Column(BigInteger, nullable=False)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    id = Column(String, primary_key=True)
    lead_id = Column(String, index=True, nullable=False)
    token_hash = Column(String, nullable=False)
    expires_at = Column(BigInteger, nullable=False)
    used_at = Column(BigInteger, nullable=True)
    created_at = Column(BigInteger, nullable=False)

class FounderEscalation(Base):
    __tablename__ = "founder_escalations"
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    thread_id = Column(String, index=True, nullable=True)
    lead_id = Column(String, nullable=True)
    user_id = Column(String, nullable=True)
    email = Column(String, nullable=True)
    full_name = Column(String, nullable=True)
    interest_type = Column(String, nullable=True)
    message = Column(Text, nullable=True)
    score = Column(Integer, nullable=False, default=0)
    status = Column(String, nullable=False, default="requested")
    consent_contact = Column(Boolean, nullable=False, default=False)
    summary = Column(Text, nullable=True)
    founder_action = Column(String, nullable=True)
    source = Column(String, nullable=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)


class RuntimeMemory(Base):
    __tablename__ = "runtime_memories"
    __table_args__ = (
        Index("ix_runtime_memories_org_user_key", "org_slug", "user_id", "memory_key"),
    )
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    user_id = Column(String, index=True, nullable=False)
    thread_id = Column(String, index=True, nullable=True)
    memory_key = Column(String, nullable=False)
    memory_value = Column(Text, nullable=False)
    source = Column(String, nullable=True)
    confidence = Column(Numeric(4, 2), nullable=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

class TrialState(Base):
    __tablename__ = "trial_states"
    __table_args__ = (
        Index("ix_trial_states_org_user", "org_slug", "user_id", unique=True),
    )
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    user_id = Column(String, index=True, nullable=False)
    trial_started_at = Column(BigInteger, nullable=False)
    last_seen_at = Column(BigInteger, nullable=False)
    activation_level = Column(String, nullable=True)
    conversion_readiness = Column(String, nullable=True)
    recommended_next_action = Column(String, nullable=True)
    numerology_invited_at = Column(BigInteger, nullable=True)
    last_activation_score = Column(Integer, nullable=True)

class TrialEvent(Base):
    __tablename__ = "trial_events"
    __table_args__ = (
        Index("ix_trial_events_org_user_created", "org_slug", "user_id", "created_at"),
    )
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    user_id = Column(String, index=True, nullable=False)
    thread_id = Column(String, index=True, nullable=True)
    event_name = Column(String, nullable=False)
    payload_json = Column(Text, nullable=True)
    created_at = Column(BigInteger, nullable=False)

class NumerologyProfile(Base):
    __tablename__ = "numerology_profiles"
    __table_args__ = (
        Index("ix_numerology_profiles_org_user", "org_slug", "user_id"),
    )
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    user_id = Column(String, index=True, nullable=False)
    preferred_name = Column(String, nullable=True)
    full_name = Column(String, nullable=False)
    birth_date = Column(String, nullable=False)
    context = Column(String, nullable=True)
    profile_json = Column(Text, nullable=False)
    consent = Column(Boolean, nullable=False, default=False)
    confirmed_at = Column(BigInteger, nullable=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)


class TrademarkMatter(Base):
    __tablename__ = "trademark_matters"
    __table_args__ = (
        Index("ix_trademark_matters_org_created", "org_slug", "created_at"),
        Index("ix_trademark_matters_org_status", "org_slug", "status"),
        Index("ix_trademark_matters_org_mark", "org_slug", "normalized_mark"),
    )
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    mark_name = Column(String, nullable=False)
    normalized_mark = Column(String, nullable=False)
    applicant_name = Column(String, nullable=True)
    applicant_country = Column(String, nullable=True)
    contact_email = Column(String, nullable=True)
    requested_by_user_id = Column(String, nullable=True)
    status = Column(String, nullable=False, default="draft")  # draft|screened|review|approved|filed|hold
    approval_status = Column(String, nullable=False, default="pending")  # pending|approved|rejected
    approval_by_user_id = Column(String, nullable=True)
    approval_at = Column(BigInteger, nullable=True)
    filing_mode = Column(String, nullable=False, default="assisted")  # assisted|manual|api_ready
    source = Column(String, nullable=True)
    jurisdictions_json = Column(Text, nullable=True)
    nice_classes_json = Column(Text, nullable=True)
    goods_services_text = Column(Text, nullable=True)
    risk_score = Column(Integer, nullable=True)
    risk_level = Column(String, nullable=True)
    internal_conflicts_json = Column(Text, nullable=True)
    external_screening_json = Column(Text, nullable=True)
    dossier_json = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)


class TrademarkEvent(Base):
    __tablename__ = "trademark_events"
    __table_args__ = (
        Index("ix_trademark_events_org_created", "org_slug", "created_at"),
        Index("ix_trademark_events_matter", "matter_id", "created_at"),
    )
    id = Column(String, primary_key=True)
    org_slug = Column(String, nullable=False)
    matter_id = Column(String, nullable=False)
    event_type = Column(String, nullable=False)
    actor_user_id = Column(String, nullable=True)
    payload_json = Column(Text, nullable=True)
    created_at = Column(BigInteger, nullable=False)


class SocialProofItem(Base):
    __tablename__ = "social_proof_items"
    __table_args__ = (
        Index("ix_social_proof_items_org_kind_status", "org_slug", "kind", "status"),
        Index("ix_social_proof_items_org_sort", "org_slug", "sort_order", "created_at"),
        Index("ix_social_proof_items_org_featured", "org_slug", "featured", "created_at"),
    )
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    page_key = Column(String, nullable=False, default="landing_home")
    kind = Column(String, nullable=False, default="testimonial")  # logo|testimonial|case|partner|badge
    status = Column(String, nullable=False, default="draft")  # draft|published|archived
    featured = Column(Boolean, nullable=False, default=False)
    title = Column(String, nullable=True)
    subtitle = Column(String, nullable=True)
    summary = Column(Text, nullable=True)
    quote = Column(Text, nullable=True)
    person_name = Column(String, nullable=True)
    person_role = Column(String, nullable=True)
    company_name = Column(String, nullable=True)
    company_site = Column(String, nullable=True)
    image_url = Column(String, nullable=True)
    logo_url = Column(String, nullable=True)
    href = Column(String, nullable=True)
    region = Column(String, nullable=True)
    market_segment = Column(String, nullable=True)
    metrics_json = Column(Text, nullable=True)
    tags_json = Column(Text, nullable=True)
    proof_code = Column(String, nullable=True)
    sort_order = Column(Integer, nullable=False, default=100)
    starts_at = Column(BigInteger, nullable=True)
    ends_at = Column(BigInteger, nullable=True)
    created_by = Column(String, nullable=True)
    updated_by = Column(String, nullable=True)
    published_at = Column(BigInteger, nullable=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)


class LandingContentBlock(Base):
    __tablename__ = "landing_content_blocks"
    __table_args__ = (
        Index("ix_landing_content_blocks_org_page_sort", "org_slug", "page_key", "sort_order"),
        Index("ix_landing_content_blocks_org_page_key", "org_slug", "page_key", "block_key", unique=True),
    )
    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False)
    page_key = Column(String, nullable=False, default="landing_home")
    block_key = Column(String, nullable=False)
    status = Column(String, nullable=False, default="draft")  # draft|published|archived
    title = Column(String, nullable=True)
    subtitle = Column(String, nullable=True)
    body = Column(Text, nullable=True)
    cta_label = Column(String, nullable=True)
    cta_href = Column(String, nullable=True)
    payload_json = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=100)
    starts_at = Column(BigInteger, nullable=True)
    ends_at = Column(BigInteger, nullable=True)
    created_by = Column(String, nullable=True)
    updated_by = Column(String, nullable=True)
    published_at = Column(BigInteger, nullable=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)


class EvolutionProposal(Base):
    __tablename__ = "evolution_proposals"
    __table_args__ = (
        Index("ix_evolution_proposals_org_status", "org_slug", "status"),
        Index("ix_evolution_proposals_status_updated", "status", "updated_at"),
        UniqueConstraint("fingerprint", name="ux_evolution_proposals_fingerprint"),
    )

    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False, default="system")
    fingerprint = Column(String, nullable=False)
    code = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    category = Column(String, nullable=False)
    source = Column(String, nullable=False)
    action = Column(String, nullable=False)
    status = Column(String, nullable=False, default="awaiting_master_approval")
    title = Column(String, nullable=True)
    summary = Column(Text, nullable=True)
    finding_json = Column(Text, nullable=True)
    issue_json = Column(Text, nullable=True)
    decision_json = Column(Text, nullable=True)
    approval_note = Column(Text, nullable=True)
    rejection_note = Column(Text, nullable=True)
    domain_scope = Column(String, nullable=True)
    recurrence_window_count = Column(Integer, nullable=False, default=1)
    blast_radius_accumulated = Column(Integer, nullable=False, default=0)
    security_accumulated = Column(Integer, nullable=False, default=0)
    last_priority_score = Column(Integer, nullable=False, default=0)
    last_recommendation = Column(String, nullable=True)
    last_cadence_seconds = Column(Integer, nullable=False, default=0)
    first_detected_at = Column(BigInteger, nullable=False, default=_now_ts)
    last_detected_at = Column(BigInteger, nullable=False, default=_now_ts)
    detected_count = Column(Integer, nullable=False, default=1)
    approved_by = Column(String, nullable=True)
    approved_at = Column(BigInteger, nullable=True)
    rejected_by = Column(String, nullable=True)
    rejected_at = Column(BigInteger, nullable=True)
    last_trace_id = Column(String, nullable=True)
    last_execution_status = Column(String, nullable=True)
    created_at = Column(BigInteger, nullable=False, default=_now_ts)
    updated_at = Column(BigInteger, nullable=False, default=_now_ts)


class EvolutionExecution(Base):
    __tablename__ = "evolution_executions"
    __table_args__ = (
        Index("ix_evolution_executions_proposal_created", "proposal_id", "created_at"),
        Index("ix_evolution_executions_status_created", "status", "created_at"),
    )

    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False, default="system")
    proposal_id = Column(String, index=True, nullable=False)
    status = Column(String, nullable=False)
    mode = Column(String, nullable=False, default="manual")
    actor_ref = Column(String, nullable=True)
    trace_id = Column(String, nullable=True)
    result_json = Column(Text, nullable=True)
    error_text = Column(Text, nullable=True)
    started_at = Column(BigInteger, nullable=True)
    completed_at = Column(BigInteger, nullable=True)
    created_at = Column(BigInteger, nullable=False, default=_now_ts)
    updated_at = Column(BigInteger, nullable=False, default=_now_ts)


class EvolutionSignalSnapshot(Base):
    __tablename__ = "evolution_signal_snapshots"
    __table_args__ = (
        Index("ix_evolution_signal_snapshots_proposal_created", "proposal_id", "created_at"),
        Index("ix_evolution_signal_snapshots_fingerprint_created", "fingerprint", "created_at"),
    )

    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False, default="system")
    proposal_id = Column(String, index=True, nullable=False)
    fingerprint = Column(String, nullable=False)
    code = Column(String, nullable=False)
    category = Column(String, nullable=False)
    domain_scope = Column(String, nullable=True)
    recurrence_window_count = Column(Integer, nullable=False, default=1)
    blast_radius_score = Column(Integer, nullable=False, default=0)
    security_score = Column(Integer, nullable=False, default=0)
    priority_score = Column(Integer, nullable=False, default=0)
    recommendation = Column(String, nullable=True)
    cadence_seconds = Column(Integer, nullable=False, default=0)
    policy_version = Column(String, nullable=True)
    trace_id = Column(String, nullable=True)
    payload_json = Column(Text, nullable=True)
    created_at = Column(BigInteger, nullable=False, default=_now_ts)


class EvolutionCycleLog(Base):
    __tablename__ = "evolution_cycle_logs"
    __table_args__ = (
        Index("ix_evolution_cycle_logs_created", "created_at"),
    )

    id = Column(String, primary_key=True)
    org_slug = Column(String, index=True, nullable=False, default="system")
    trace_id = Column(String, nullable=True)
    findings = Column(Integer, nullable=False, default=0)
    classified = Column(Integer, nullable=False, default=0)
    proposals_touched = Column(Integer, nullable=False, default=0)
    proposals_created = Column(Integer, nullable=False, default=0)
    proposals_suppressed = Column(Integer, nullable=False, default=0)
    max_priority_score = Column(Integer, nullable=False, default=0)
    avg_priority_score = Column(Integer, nullable=False, default=0)
    next_interval_suggested_seconds = Column(Integer, nullable=False, default=0)
    recommendation_buckets_json = Column(Text, nullable=True)
    domain_buckets_json = Column(Text, nullable=True)
    top_queue_json = Column(Text, nullable=True)
    policy_version = Column(String, nullable=True)
    created_at = Column(BigInteger, nullable=False, default=_now_ts)
