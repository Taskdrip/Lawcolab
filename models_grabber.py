"""
LawColab — CRM Grabber / Research Robot Models
Tables: research_sessions, grabbed_results, social_engagements
"""
from app import db
from sqlalchemy import Integer, String, Text, Boolean, DateTime, Float, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime


class ResearchSession(db.Model):
    """Tracks every search/scan session run by the research robot."""
    __tablename__ = "research_sessions"

    id            = db.Column(Integer, primary_key=True)
    keyword       = db.Column(String(300), nullable=False)
    platform      = db.Column(String(60),  nullable=False)   # google_gmb | quora | facebook | linkedin | reddit | twitter | web
    search_type   = db.Column(String(60),  default="community")  # community | gmb_listing | quora_question | web
    country       = db.Column(String(100))
    results_found = db.Column(Integer, default=0)
    results_added = db.Column(Integer, default=0)
    status        = db.Column(String(30),  default="pending")  # pending | running | done | error
    error_message = db.Column(Text)
    run_by_id     = db.Column(String,  db.ForeignKey("users.id"), nullable=True)
    created_at    = db.Column(DateTime, default=datetime.utcnow)
    completed_at  = db.Column(DateTime)

    results = relationship("GrabbedResult", back_populates="session", cascade="all, delete-orphan")
    run_by  = relationship("User", foreign_keys=[run_by_id])

    @property
    def duration_seconds(self):
        if self.completed_at and self.created_at:
            return int((self.completed_at - self.created_at).total_seconds())
        return None


class GrabbedResult(db.Model):
    """
    Staging table — one row per scraped result before it is pushed to CRM or Directory.
    result_type: 'community' → SocialCommunity, 'listing' → DirectoryLawFirm
    """
    __tablename__ = "grabbed_results"

    id           = db.Column(Integer, primary_key=True)
    session_id   = db.Column(Integer, db.ForeignKey("research_sessions.id"), nullable=False)
    result_type  = db.Column(String(30), default="community")  # community | listing
    platform     = db.Column(String(60))

    # Common fields
    name         = db.Column(String(300))
    url          = db.Column(String(1000))
    description  = db.Column(Text)
    snippet      = db.Column(Text)       # raw snippet from search engine
    thumbnail    = db.Column(String(500))

    # Community-specific
    member_count       = db.Column(Integer)
    member_count_text  = db.Column(String(50))
    category           = db.Column(String(100))
    country_focus      = db.Column(String(100))
    join_link          = db.Column(String(1000))

    # Listing-specific (GMB)
    phone        = db.Column(String(50))
    email        = db.Column(String(200))
    address      = db.Column(String(500))
    city         = db.Column(String(100))
    state        = db.Column(String(100))
    country      = db.Column(String(100))
    rating       = db.Column(Float)
    reviews      = db.Column(Integer)
    website      = db.Column(String(500))
    place_id     = db.Column(String(200))

    # Status
    status       = db.Column(String(30), default="pending")   # pending | added_crm | added_directory | added_community | skipped | duplicate
    crm_id       = db.Column(Integer)    # ID of the record created in CRM/Directory
    notes        = db.Column(Text)

    raw_json     = db.Column(Text)       # full raw payload from scraper
    created_at   = db.Column(DateTime, default=datetime.utcnow)

    session = relationship("ResearchSession", back_populates="results")

    @property
    def is_added(self):
        return self.status in ("added_crm", "added_directory", "added_community")


class SocialEngagement(db.Model):
    """
    Tracks every comment, post, share, or reply made from the in-app
    browser on Facebook, LinkedIn, Reddit, Quora, etc.
    """
    __tablename__ = "social_engagements"

    id              = db.Column(Integer, primary_key=True)
    platform        = db.Column(String(60), nullable=False)     # facebook | linkedin | reddit | quora | twitter | youtube
    engagement_type = db.Column(String(40), default="comment")  # comment | post | share | reply | like | dm
    target_url      = db.Column(String(1000))   # URL of the group/page/post we engaged with
    target_name     = db.Column(String(300))    # Name of the group/community
    post_content    = db.Column(Text)           # What we wrote
    post_url        = db.Column(String(1000))   # URL of our actual post/comment (if known)
    image_url       = db.Column(String(500))    # Attached image (if any)
    hashtags        = db.Column(String(500))
    status          = db.Column(String(30), default="posted")   # drafted | posted | failed | scheduled
    scheduled_at    = db.Column(DateTime)
    posted_at       = db.Column(DateTime, default=datetime.utcnow)

    # Tracking metrics
    views           = db.Column(Integer, default=0)
    likes           = db.Column(Integer, default=0)
    comments        = db.Column(Integer, default=0)
    shares          = db.Column(Integer, default=0)
    clicks          = db.Column(Integer, default=0)
    last_checked_at = db.Column(DateTime)

    # Link to a CRM firm or community (optional)
    linked_firm_id      = db.Column(Integer, db.ForeignKey("directory_law_firms.id"), nullable=True)
    linked_community_id = db.Column(Integer, db.ForeignKey("social_communities.id"), nullable=True)

    posted_by_id    = db.Column(String, db.ForeignKey("users.id"), nullable=True)
    campaign_tag    = db.Column(String(200))
    notes           = db.Column(Text)
    created_at      = db.Column(DateTime, default=datetime.utcnow)
    updated_at      = db.Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    posted_by        = relationship("User", foreign_keys=[posted_by_id])
    linked_firm      = relationship("DirectoryLawFirm", foreign_keys=[linked_firm_id])
    linked_community = relationship("SocialCommunity",  foreign_keys=[linked_community_id])

    @property
    def engagement_score(self):
        return (self.likes or 0) + (self.comments or 0) * 2 + (self.shares or 0) * 3 + (self.clicks or 0)
