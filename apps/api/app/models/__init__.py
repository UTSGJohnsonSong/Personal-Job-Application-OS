"""Import all models so SQLAlchemy metadata is fully populated.

Alembic and create_all rely on this module importing every mapped class.
"""

from app.db.base import Base  # noqa: F401
from app.models.ammo import AmmoBlock  # noqa: F401
from app.models.application import (  # noqa: F401
    Application,
    ApplicationAnswer,
    ApplicationConfirmation,
    ApplicationEvent,
    ApplicationPacket,
    GeneratedDocument,
)
from app.models.matching import (  # noqa: F401
    EligibilityResult,
    JobMatch,
    MatchDimension,
    MatchEvidence,
    RankingProfile,
    RankingVersion,
)
from app.models.ops import (  # noqa: F401
    AuditLog,
    ConnectorFailure,
    EmailConnection,
    EmailEvent,
    LearningUpdate,
    ModelRun,
    Notification,
    UserFeedback,
)
from app.models.personal import (  # noqa: F401
    ApplicationPreference,
    CandidateEducation,
    CandidateExperience,
    CandidateProfile,
    CandidateProject,
    CandidateSkill,
    PersonalContextItem,
    StandardAnswer,
    WorkAuthorization,
)
from app.models.resume import (  # noqa: F401
    Document,
    ResumeBullet,
    ResumeSection,
    ResumeVersion,
)
from app.models.sourcing import (  # noqa: F401
    Company,
    CompanyAlias,
    CompanyCareerPage,
    CompanyDomain,
    DuplicateGroup,
    Job,
    JobEmbedding,
    JobLocation,
    JobRequirement,
    JobSnapshot,
    JobSource,
    SourceSyncRun,
)
from app.models.user import User, UserSettings  # noqa: F401

__all__ = ["Base"]
