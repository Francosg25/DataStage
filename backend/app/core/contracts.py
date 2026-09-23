"""Public response contracts shared by OpenAPI and the Angular client."""
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel


class RunCounts(BaseModel):
    receivedFiles: int
    processedFiles: int
    skippedFiles: int
    failedFiles: int
    processedTables: int
    rows: int
    warnings: int
    errors: int


class RunResponse(BaseModel):
    id: str
    kind: Literal["monthly", "annual"]
    period: str | None
    year: int
    rangeName: str | None
    status: Literal["queued", "running", "completed", "needs_attention", "failed"]
    phase: str
    progress: int
    functionalResult: Literal["OK", "WARNING"] | None
    publicationStatus: str
    exportStatus: str
    createdAt: str
    updatedAt: str
    counts: RunCounts
    exportDocumentId: str | None
    errorMessage: str | None
    periodVersion: int
    engineVersion: str
    parentRunId: str | None


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int


class FileRow(BaseModel):
    id: str
    fileName: str
    tableCode: str
    status: str
    message: str
    rowCount: int
    columnCount: int
    dateColumnCount: int


class TableRow(BaseModel):
    tableCode: str
    sheetName: str
    rowCount: int
    columnCount: int
    dateColumnCount: int
    headers: list[str]


class IssueRow(BaseModel):
    id: str
    severity: str
    code: str
    message: str
    fileId: str | None
    rowNumber: int | None
    columnName: str | None


class DataPage(Page[dict[str, Any]]):
    headers: list[str]
    tableName: str


class Problem(BaseModel):
    type: str
    title: str
    status: int
    detail: str
    instance: str
    correlationId: str = ""
