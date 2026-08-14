"""
Pydantic response contracts for the EnerGov search/search endpoint.

Field names and nullability were taken directly from real responses
captured in the spike (see spike/probe_search.py and PROJECT.md), not
guessed. Every model uses extra="forbid": this API is undocumented and can
change shape under us at any time, and per PROJECT.md the primary defense
against that is noticing loudly (a validation error) rather than silently
passing unknown fields through.

The single search endpoint returns records from several different EnerGov
modules (permits, plans, inspections, licenses, projects, ...) in one
shared envelope. This model targets what a Permit-module record looks like;
fields that were consistently populated across every permit record observed
are required, fields that were null are Optional.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Highlight(BaseModel):
    model_config = ConfigDict(extra="forbid")

    DocumentId: str
    Field: str
    FriendlyName: Optional[str] = None
    HighlightText: str
    ChildIndex: int
    ShowInFooter: bool


class RecordAddress(BaseModel):
    """Named RecordAddress, not Address: a field below is also named
    `Address`, and pydantic mis-resolves `Address: Optional[Address]` (the
    field shadows the class in its self-reference namespace, silently
    collapsing the type to NoneType). Confirmed empirically, 2026-08-14."""

    model_config = ConfigDict(extra="forbid")

    CountryTypeId: int
    CountryTypeName: Optional[str] = None
    CountryName: Optional[str] = None
    StreetTypeName: str
    PreDirection: str
    PostDirection: str
    AddressLine1: str
    AddressLine2: str
    AddressLine3: str
    AddressTypeName: str
    UnitOrSuite: str
    City: Optional[str] = None
    StateName: str
    ProvinceName: str
    RuralRoute: str
    POBox: str
    Station: str
    CompSite: str
    ATTN: str
    PostalCode: str
    IsMain: bool
    FullAddress: str


class SearchResultRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    CaseId: UUID
    CaseNumber: str
    CaseTypeId: UUID
    CaseType: str
    CaseWorkclassId: Optional[UUID] = None
    CaseWorkclass: Optional[str] = None
    CaseStatusId: UUID
    CaseStatus: str
    ProjectName: Optional[str] = None
    IssueDate: Optional[datetime] = None
    ApplyDate: Optional[datetime] = None
    ExpireDate: Optional[datetime] = None
    CompleteDate: Optional[datetime] = None
    FinalDate: Optional[datetime] = None
    RequestDate: Optional[datetime] = None
    ScheduleDate: Optional[datetime] = None
    StartDate: Optional[datetime] = None
    ExpectedEndDate: Optional[datetime] = None
    Address: Optional[RecordAddress] = None
    ModuleName: int
    AddressDisplay: str
    MainParcel: Optional[str] = None
    Description: Optional[str] = None
    DBA: Optional[str] = None
    LicenseYear: Optional[str] = None
    CompanyName: Optional[str] = None
    CompanyTypeName: Optional[str] = None
    BusinessTypeName: Optional[str] = None
    TaxID: Optional[str] = None
    OpenedDate: Optional[datetime] = None
    ClosedDate: Optional[datetime] = None
    LastAuditDate: Optional[datetime] = None
    HolderCompanyName: Optional[str] = None
    HolderFirstName: Optional[str] = None
    HolderLastName: Optional[str] = None
    HolderMiddleName: Optional[str] = None
    BusinessId: Optional[str] = None
    BusinessStatus: Optional[str] = None
    Highlights: list[Highlight]


class SearchResultPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    EntityResults: list[SearchResultRecord]
    TotalPages: int
    PermitsFound: int
    PlansFound: int
    InspectionsFound: int
    CodeCasesFound: int
    RequestsFound: int
    BusinessLicensesFound: int
    ProfessionalLicensesFound: int
    LicensesFound: int
    ProjectsFound: int
    OperationalPermitsFound: int
    TotalFound: int


class SearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    Result: SearchResultPayload
    Success: bool
    ErrorMessage: str
    ValidationErrorMessage: str
    ConcurrencyErrorMessage: str
    StatusCode: int
    BrokenRules: list[str]


class InspectionRecord(BaseModel):
    """UNCONFIRMED, unlike every other model in this file — read before
    trusting this one.

    entity/inspections/search/search requires the caller to be an
    authenticated "contact" on the permit (confirmed empirically against
    two independent real permits, 2026-08-14: both anonymous calls got
    Result=null back, never a populated list — see InspectionSearchResponse
    below). v1 explicitly excludes login (see PROJECT.md), so we could never
    capture a real populated response to model this from.

    Field names below are inferred from the *client-side* Angular code in
    the same app bundle that reads Inspection objects for the "Today's
    Inspections" public page (TodaysInspectionExportConstant's column
    list) — same backend Inspection entity, a different and genuinely
    public endpoint, not a guess out of nowhere, but also not a captured
    response for *this* endpoint. Deliberately NOT extra="forbid" for that
    reason: a guessed strict schema would be as likely to reject real data
    as accept it. Replace this model (and tighten it to extra="forbid")
    the first time Result is ever actually observed non-null.
    """

    model_config = ConfigDict(extra="allow")

    InspectionNumber: Optional[str] = None
    CaseNumber: Optional[str] = None
    CaseType: Optional[str] = None
    InspectionTypeName: Optional[str] = None
    Address: Optional[str] = None
    PrimaryInspectorName: Optional[str] = None
    StartTime: Optional[datetime] = None
    EndTime: Optional[datetime] = None
    InspectorPhoneNumber: Optional[str] = None
    InspectionStatusName: Optional[str] = None
    InspectionOrder: Optional[int] = None


class InspectionSearchResponse(BaseModel):
    """Envelope for entity/inspections/search/search. This part IS
    confirmed against real live responses (2026-08-14, two independent
    permits): both returned exactly this shape with Result=null,
    Success=false, StatusCode=412, ErrorMessage="You must be a contact on
    this record to see this information". For this project's anonymous
    public client, that is the expected outcome for every permit, not a
    transient failure.

    NOTE: this endpoint (the authoritative, complete per-permit inspection
    list) is NOT what get_inspection_history uses as of 2026-08-14 — see
    InspectionDetail below and PROJECT.md for why. Kept here as accurate
    documentation of a real, confirmed-gated endpoint, not dead code."""

    model_config = ConfigDict(extra="forbid")

    Result: Optional[list[InspectionRecord]] = None
    Success: bool
    ErrorMessage: str
    ValidationErrorMessage: str
    ConcurrencyErrorMessage: str
    StatusCode: int
    BrokenRules: list[str]


class InspectionDetail(BaseModel):
    """A single inspection's full detail, from
    /apps/selfservice/api/energov/inspections/getById/{InspectionId}.

    Unlike InspectionRecord above, this one IS captured from a real,
    successful, anonymous (no login) response (2026-08-14) — see
    PROJECT.md. LinkTypeName/LinkNumber/LinkId are the load-bearing fields:
    they're an exact link back to the parent permit (LinkId matched a known
    permit's CaseId GUID exactly), which is what makes the
    address-search-then-verify design in get_inspection_history authoritative
    per-record even though candidate discovery itself is best-effort.

    Nullability: fields that are clearly structural (IDs, type/status
    names, the Link*/permission-flag fields) are required, since they were
    present and non-null on the one real record captured. Fields that
    describe inspection-instance state that plausibly wouldn't exist yet
    for a requested-but-not-yet-completed inspection (Actual* timestamps,
    assigned-inspector fields, Comment) are marked Optional even though
    populated in the one sample seen, since an inspection record earlier in
    its lifecycle would very plausibly have these unset. This is a
    reasoned inference from n=1, not n>1 confirmation like most of this
    file — tighten if a null is ever observed disagreeing with a
    non-Optional field here."""

    model_config = ConfigDict(extra="forbid")

    InspectionId: UUID
    InspectionNumber: str
    TypeName: str
    StatusName: str
    EnteredDate: Optional[datetime] = None
    RequestDate: Optional[datetime] = None
    RequestTime: Optional[str] = None
    ScheduledDate: Optional[datetime] = None
    ScheduledStartTime: Optional[str] = None
    ScheduledEndDate: Optional[datetime] = None
    ActualDate: Optional[datetime] = None
    ActualEndDate: Optional[datetime] = None
    ActualEndTime: Optional[str] = None
    MainAddress: str
    MainParcel: Optional[str] = None
    AssignedInspectorFirstName: Optional[str] = None
    AssignedInspectorLastName: Optional[str] = None
    AssignedInspectorName: Optional[str] = None
    AssignedInspectorEmail: Optional[str] = None
    AssignedInspectorPhoneNumber: Optional[str] = None
    IsReinspection: bool
    LinkTypeName: str
    LinkNumber: str
    LinkId: UUID
    Order: int
    CustomFieldLayoutId: Optional[UUID] = None
    OnlineCustomFieldLayoutId: Optional[UUID] = None
    HasAuthorizedContact: bool
    IsLoggedIn: bool
    IsEntityContact: bool
    CanCancelInspection: bool
    ShowRescheduleButton: bool
    InspectionTypeId: UUID
    IsMidnightRequestTime: bool
    IsMidnightCompletedTime: bool
    HideRequestTime: bool
    Comment: Optional[str] = None
    InspectionTypeModuleId: int
    ShowPrint: bool
    ShowRequestedTime: str
    ShowScheduledTime: str
    RequestedAMText: Optional[str] = None
    RequestedPMText: Optional[str] = None
    ScheduledAMText: Optional[str] = None
    ScheduledPMText: Optional[str] = None
    TimeZone: str
    IsMidnightScheduleTime: bool
    HideScheduleTime: bool
    ShowInspectionCommentAsAlert: int
    ShowCommentsForInspectionRequestedAfter: Optional[datetime] = None


class InspectionDetailResponse(BaseModel):
    """Envelope for inspections/getById. Confirmed live, 2026-08-14."""

    model_config = ConfigDict(extra="forbid")

    Result: InspectionDetail
    Success: bool
    ErrorMessage: str
    ValidationErrorMessage: str
    ConcurrencyErrorMessage: str
    StatusCode: int
    BrokenRules: list[str]
