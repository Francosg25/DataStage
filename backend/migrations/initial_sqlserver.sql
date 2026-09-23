BEGIN TRANSACTION;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

GO

-- Running upgrade  -> 20260922_0001

CREATE TABLE agent_conversations (
    scope_id NVARCHAR(100) NOT NULL, 
    user_id NVARCHAR(200) NOT NULL, 
    created_at DATETIME2 NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    PRIMARY KEY (id)
);

GO

CREATE TABLE periods (
    scope_id NVARCHAR(100) NOT NULL, 
    year INTEGER NOT NULL, 
    month INTEGER NOT NULL, 
    name NVARCHAR(100) NOT NULL, 
    active_run_id VARCHAR(36) NULL, 
    version INTEGER NOT NULL DEFAULT '0', 
    id VARCHAR(36) NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_period_month CHECK (month >= 1 AND month <= 12), 
    CONSTRAINT uq_period_scope_year_month UNIQUE (scope_id, year, month)
);

GO

CREATE TABLE agent_messages (
    conversation_id VARCHAR(36) NOT NULL, 
    role VARCHAR(30) NOT NULL, 
    content NVARCHAR(max) NOT NULL, 
    created_at DATETIME2 NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(conversation_id) REFERENCES agent_conversations (id)
);

GO

CREATE TABLE processing_runs (
    scope_id NVARCHAR(100) NOT NULL, 
    kind VARCHAR(20) NOT NULL, 
    period_id VARCHAR(36) NULL, 
    year INTEGER NOT NULL, 
    range_name NVARCHAR(100) NULL, 
    status VARCHAR(30) NOT NULL, 
    phase VARCHAR(50) NOT NULL, 
    progress INTEGER NOT NULL, 
    functional_result VARCHAR(20) NULL, 
    publication_status VARCHAR(30) NOT NULL, 
    export_status VARCHAR(30) NOT NULL, 
    created_by NVARCHAR(200) NOT NULL, 
    created_at DATETIME2 NOT NULL, 
    updated_at DATETIME2 NOT NULL, 
    engine_version VARCHAR(40) NOT NULL, 
    options_json NVARCHAR(max) NOT NULL, 
    input_fingerprint VARCHAR(64) NOT NULL, 
    expected_period_version INTEGER NOT NULL, 
    parent_run_id VARCHAR(36) NULL, 
    source_manifest_json NVARCHAR(max) NOT NULL, 
    result_document_id VARCHAR(36) NULL, 
    export_document_id VARCHAR(36) NULL, 
    error_message NVARCHAR(max) NULL, 
    counts_json NVARCHAR(max) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(parent_run_id) REFERENCES processing_runs (id), 
    FOREIGN KEY(period_id) REFERENCES periods (id), 
    CONSTRAINT uq_run_scope_fingerprint UNIQUE (scope_id, input_fingerprint)
);

GO

CREATE INDEX ix_runs_scope_created ON processing_runs (scope_id, created_at);

GO

CREATE TABLE annual_sources (
    annual_run_id VARCHAR(36) NOT NULL, 
    monthly_run_id VARCHAR(36) NOT NULL, 
    period_id VARCHAR(36) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(annual_run_id) REFERENCES processing_runs (id), 
    FOREIGN KEY(monthly_run_id) REFERENCES processing_runs (id), 
    FOREIGN KEY(period_id) REFERENCES periods (id), 
    CONSTRAINT uq_annual_monthly_source UNIQUE (annual_run_id, monthly_run_id)
);

GO

CREATE TABLE audit_events (
    scope_id NVARCHAR(100) NOT NULL, 
    run_id VARCHAR(36) NULL, 
    actor NVARCHAR(200) NOT NULL, 
    action VARCHAR(100) NOT NULL, 
    details_json NVARCHAR(max) NOT NULL, 
    created_at DATETIME2 NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(run_id) REFERENCES processing_runs (id)
);

GO

CREATE INDEX ix_audit_scope_created ON audit_events (scope_id, created_at);

GO

CREATE TABLE idempotency_requests (
    scope_id NVARCHAR(100) NOT NULL, 
    [key] NVARCHAR(200) NOT NULL, 
    request_hash VARCHAR(64) NOT NULL, 
    run_id VARCHAR(36) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(run_id) REFERENCES processing_runs (id), 
    CONSTRAINT uq_idempotency_scope_key UNIQUE (scope_id, [key])
);

GO

CREATE TABLE outbox_messages (
    run_id VARCHAR(36) NOT NULL, 
    event_type VARCHAR(100) NOT NULL, 
    payload_json NVARCHAR(max) NOT NULL, 
    status VARCHAR(30) NOT NULL, 
    created_at DATETIME2 NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(run_id) REFERENCES processing_runs (id)
);

GO

CREATE INDEX ix_outbox_pending ON outbox_messages (status, created_at);

GO

CREATE TABLE processing_jobs (
    run_id VARCHAR(36) NOT NULL, 
    kind VARCHAR(30) NOT NULL, 
    status VARCHAR(30) NOT NULL, 
    attempts INTEGER NOT NULL, 
    available_at DATETIME2 NOT NULL, 
    lease_until DATETIME2 NULL, 
    lease_owner VARCHAR(100) NULL, 
    fence INTEGER NOT NULL, 
    payload_json NVARCHAR(max) NOT NULL, 
    last_error NVARCHAR(max) NULL, 
    created_at DATETIME2 NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(run_id) REFERENCES processing_runs (id)
);

GO

CREATE INDEX ix_jobs_claim ON processing_jobs (status, available_at);

GO

CREATE INDEX ix_jobs_run ON processing_jobs (run_id);

GO

CREATE TABLE processing_tables (
    run_id VARCHAR(36) NOT NULL, 
    table_code NVARCHAR(100) NOT NULL, 
    sheet_name NVARCHAR(31) NOT NULL, 
    row_count INTEGER NOT NULL, 
    column_count INTEGER NOT NULL, 
    date_column_count INTEGER NOT NULL, 
    headers_json NVARCHAR(max) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(run_id) REFERENCES processing_runs (id), 
    CONSTRAINT uq_processing_table_run_code UNIQUE (run_id, table_code)
);

GO

CREATE TABLE stored_documents (
    scope_id NVARCHAR(100) NOT NULL, 
    run_id VARCHAR(36) NULL, 
    kind VARCHAR(30) NOT NULL, 
    original_name NVARCHAR(512) NOT NULL, 
    storage_key NVARCHAR(512) NOT NULL, 
    sha256 VARCHAR(64) NOT NULL, 
    size_bytes BIGINT NOT NULL, 
    status VARCHAR(30) NOT NULL, 
    created_at DATETIME2 NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(run_id) REFERENCES processing_runs (id)
);

GO

CREATE INDEX ix_documents_scope_sha ON stored_documents (scope_id, sha256);

GO

CREATE TABLE processing_files (
    run_id VARCHAR(36) NOT NULL, 
    period_id VARCHAR(36) NULL, 
    document_id VARCHAR(36) NULL, 
    file_name NVARCHAR(512) NOT NULL, 
    table_code NVARCHAR(100) NOT NULL, 
    folio NVARCHAR(512) NOT NULL, 
    sha256 VARCHAR(64) NOT NULL, 
    ordinal INTEGER NOT NULL, 
    status VARCHAR(30) NOT NULL, 
    message NVARCHAR(max) NOT NULL, 
    row_count INTEGER NOT NULL, 
    column_count INTEGER NOT NULL, 
    date_column_count INTEGER NOT NULL, 
    headers_json NVARCHAR(max) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(document_id) REFERENCES stored_documents (id), 
    FOREIGN KEY(period_id) REFERENCES periods (id), 
    FOREIGN KEY(run_id) REFERENCES processing_runs (id), 
    CONSTRAINT uq_file_run_ordinal UNIQUE (run_id, ordinal)
);

GO

CREATE INDEX ix_files_run ON processing_files (run_id);

GO

CREATE TABLE ds_501 (
    id BIGINT NOT NULL IDENTITY, 
    period_id VARCHAR(36) NOT NULL, 
    processing_run_id VARCHAR(36) NOT NULL, 
    processing_file_id VARCHAR(36) NOT NULL, 
    archivo_origen NVARCHAR(512) NOT NULL, 
    folio_origen NVARCHAR(512) NOT NULL, 
    table_code NVARCHAR(100) NOT NULL, 
    ingested_at DATETIME2 NOT NULL, 
    source_row_number INTEGER NOT NULL, 
    original_dates_json NVARCHAR(max) NOT NULL, 
    pedimento_completo NVARCHAR(450) NULL, 
    patente NVARCHAR(max) NULL, 
    pedimento NVARCHAR(max) NULL, 
    seccion_aduanera NVARCHAR(max) NULL, 
    tipo_operacion NVARCHAR(max) NULL, 
    clave_documento NVARCHAR(max) NULL, 
    seccion_aduanera_entrada NVARCHAR(max) NULL, 
    curp_contribuyente NVARCHAR(max) NULL, 
    rfc NVARCHAR(max) NULL, 
    curp_agente_a NVARCHAR(max) NULL, 
    tipo_cambio NVARCHAR(max) NULL, 
    total_fletes NVARCHAR(max) NULL, 
    total_seguros NVARCHAR(max) NULL, 
    total_embalajes NVARCHAR(max) NULL, 
    total_incrementables NVARCHAR(max) NULL, 
    total_deducibles NVARCHAR(max) NULL, 
    peso_bruto_mercancia NVARCHAR(max) NULL, 
    medio_transporte_salida NVARCHAR(max) NULL, 
    medio_transporte_arribo NVARCHAR(max) NULL, 
    medio_transporte_entrada_salida NVARCHAR(max) NULL, 
    destino_mercancia NVARCHAR(max) NULL, 
    nombre_contribuyente NVARCHAR(max) NULL, 
    calle_contribuyente NVARCHAR(max) NULL, 
    num_interior_contribuyente NVARCHAR(max) NULL, 
    num_exterior_contribuyente NVARCHAR(max) NULL, 
    cp_contribuyente NVARCHAR(max) NULL, 
    municipio_contribuyente NVARCHAR(max) NULL, 
    entidad_fed_contribuyente NVARCHAR(max) NULL, 
    pais_contribuyente NVARCHAR(max) NULL, 
    tipo_pedimento NVARCHAR(max) NULL, 
    fecha_recepcion_pedimento DATETIME2 NULL, 
    fecha_pago_real DATETIME2 NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(period_id) REFERENCES periods (id), 
    FOREIGN KEY(processing_file_id) REFERENCES processing_files (id), 
    FOREIGN KEY(processing_run_id) REFERENCES processing_runs (id), 
    CONSTRAINT uq_ds_501_source UNIQUE (processing_run_id, processing_file_id, source_row_number)
);

GO

CREATE INDEX ix_ds_501_pedimento ON ds_501 (pedimento_completo);

GO

CREATE INDEX ix_ds_501_period ON ds_501 (period_id);

GO

CREATE INDEX ix_ds_501_run ON ds_501 (processing_run_id);

GO

CREATE TABLE ds_502 (
    id BIGINT NOT NULL IDENTITY, 
    period_id VARCHAR(36) NOT NULL, 
    processing_run_id VARCHAR(36) NOT NULL, 
    processing_file_id VARCHAR(36) NOT NULL, 
    archivo_origen NVARCHAR(512) NOT NULL, 
    folio_origen NVARCHAR(512) NOT NULL, 
    table_code NVARCHAR(100) NOT NULL, 
    ingested_at DATETIME2 NOT NULL, 
    source_row_number INTEGER NOT NULL, 
    original_dates_json NVARCHAR(max) NOT NULL, 
    pedimento_completo NVARCHAR(450) NULL, 
    patente NVARCHAR(max) NULL, 
    pedimento NVARCHAR(max) NULL, 
    seccion_aduanera NVARCHAR(max) NULL, 
    rfc_transportista NVARCHAR(max) NULL, 
    curp_transportista NVARCHAR(max) NULL, 
    nombre_transportista NVARCHAR(max) NULL, 
    pais_transporte NVARCHAR(max) NULL, 
    identificador_transporte NVARCHAR(max) NULL, 
    fecha_pago_real DATETIME2 NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(period_id) REFERENCES periods (id), 
    FOREIGN KEY(processing_file_id) REFERENCES processing_files (id), 
    FOREIGN KEY(processing_run_id) REFERENCES processing_runs (id), 
    CONSTRAINT uq_ds_502_source UNIQUE (processing_run_id, processing_file_id, source_row_number)
);

GO

CREATE INDEX ix_ds_502_pedimento ON ds_502 (pedimento_completo);

GO

CREATE INDEX ix_ds_502_period ON ds_502 (period_id);

GO

CREATE INDEX ix_ds_502_run ON ds_502 (processing_run_id);

GO

CREATE TABLE ds_503 (
    id BIGINT NOT NULL IDENTITY, 
    period_id VARCHAR(36) NOT NULL, 
    processing_run_id VARCHAR(36) NOT NULL, 
    processing_file_id VARCHAR(36) NOT NULL, 
    archivo_origen NVARCHAR(512) NOT NULL, 
    folio_origen NVARCHAR(512) NOT NULL, 
    table_code NVARCHAR(100) NOT NULL, 
    ingested_at DATETIME2 NOT NULL, 
    source_row_number INTEGER NOT NULL, 
    original_dates_json NVARCHAR(max) NOT NULL, 
    pedimento_completo NVARCHAR(450) NULL, 
    patente NVARCHAR(max) NULL, 
    pedimento NVARCHAR(max) NULL, 
    seccion_aduanera NVARCHAR(max) NULL, 
    numero_guia NVARCHAR(max) NULL, 
    tipo_guia NVARCHAR(max) NULL, 
    fecha_pago_real DATETIME2 NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(period_id) REFERENCES periods (id), 
    FOREIGN KEY(processing_file_id) REFERENCES processing_files (id), 
    FOREIGN KEY(processing_run_id) REFERENCES processing_runs (id), 
    CONSTRAINT uq_ds_503_source UNIQUE (processing_run_id, processing_file_id, source_row_number)
);

GO

CREATE INDEX ix_ds_503_pedimento ON ds_503 (pedimento_completo);

GO

CREATE INDEX ix_ds_503_period ON ds_503 (period_id);

GO

CREATE INDEX ix_ds_503_run ON ds_503 (processing_run_id);

GO

CREATE TABLE ds_504 (
    id BIGINT NOT NULL IDENTITY, 
    period_id VARCHAR(36) NOT NULL, 
    processing_run_id VARCHAR(36) NOT NULL, 
    processing_file_id VARCHAR(36) NOT NULL, 
    archivo_origen NVARCHAR(512) NOT NULL, 
    folio_origen NVARCHAR(512) NOT NULL, 
    table_code NVARCHAR(100) NOT NULL, 
    ingested_at DATETIME2 NOT NULL, 
    source_row_number INTEGER NOT NULL, 
    original_dates_json NVARCHAR(max) NOT NULL, 
    pedimento_completo NVARCHAR(450) NULL, 
    patente NVARCHAR(max) NULL, 
    pedimento NVARCHAR(max) NULL, 
    seccion_aduanera NVARCHAR(max) NULL, 
    num_contenedor NVARCHAR(max) NULL, 
    tipo_contenedor NVARCHAR(max) NULL, 
    fecha_pago_real DATETIME2 NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(period_id) REFERENCES periods (id), 
    FOREIGN KEY(processing_file_id) REFERENCES processing_files (id), 
    FOREIGN KEY(processing_run_id) REFERENCES processing_runs (id), 
    CONSTRAINT uq_ds_504_source UNIQUE (processing_run_id, processing_file_id, source_row_number)
);

GO

CREATE INDEX ix_ds_504_pedimento ON ds_504 (pedimento_completo);

GO

CREATE INDEX ix_ds_504_period ON ds_504 (period_id);

GO

CREATE INDEX ix_ds_504_run ON ds_504 (processing_run_id);

GO

CREATE TABLE ds_505 (
    id BIGINT NOT NULL IDENTITY, 
    period_id VARCHAR(36) NOT NULL, 
    processing_run_id VARCHAR(36) NOT NULL, 
    processing_file_id VARCHAR(36) NOT NULL, 
    archivo_origen NVARCHAR(512) NOT NULL, 
    folio_origen NVARCHAR(512) NOT NULL, 
    table_code NVARCHAR(100) NOT NULL, 
    ingested_at DATETIME2 NOT NULL, 
    source_row_number INTEGER NOT NULL, 
    original_dates_json NVARCHAR(max) NOT NULL, 
    pedimento_completo NVARCHAR(450) NULL, 
    patente NVARCHAR(max) NULL, 
    pedimento NVARCHAR(max) NULL, 
    seccion_aduanera NVARCHAR(max) NULL, 
    fecha_facturacion DATETIME2 NULL, 
    numero_factura NVARCHAR(max) NULL, 
    termino_facturacion NVARCHAR(max) NULL, 
    moneda_facturacion NVARCHAR(max) NULL, 
    valor_dolares NVARCHAR(max) NULL, 
    valor_moneda_extranjera NVARCHAR(max) NULL, 
    pais_facturacion NVARCHAR(max) NULL, 
    entidad_fed_facturacion NVARCHAR(max) NULL, 
    indent_fiscal_proveedor NVARCHAR(max) NULL, 
    proveedor_mercancia NVARCHAR(max) NULL, 
    calle_proveedor NVARCHAR(max) NULL, 
    num_interior_proveedor NVARCHAR(max) NULL, 
    num_exterior_proveedor NVARCHAR(max) NULL, 
    cp_proveedor NVARCHAR(max) NULL, 
    municipio_proveedor NVARCHAR(max) NULL, 
    fecha_pago_real DATETIME2 NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(period_id) REFERENCES periods (id), 
    FOREIGN KEY(processing_file_id) REFERENCES processing_files (id), 
    FOREIGN KEY(processing_run_id) REFERENCES processing_runs (id), 
    CONSTRAINT uq_ds_505_source UNIQUE (processing_run_id, processing_file_id, source_row_number)
);

GO

CREATE INDEX ix_ds_505_pedimento ON ds_505 (pedimento_completo);

GO

CREATE INDEX ix_ds_505_period ON ds_505 (period_id);

GO

CREATE INDEX ix_ds_505_run ON ds_505 (processing_run_id);

GO

CREATE TABLE ds_506 (
    id BIGINT NOT NULL IDENTITY, 
    period_id VARCHAR(36) NOT NULL, 
    processing_run_id VARCHAR(36) NOT NULL, 
    processing_file_id VARCHAR(36) NOT NULL, 
    archivo_origen NVARCHAR(512) NOT NULL, 
    folio_origen NVARCHAR(512) NOT NULL, 
    table_code NVARCHAR(100) NOT NULL, 
    ingested_at DATETIME2 NOT NULL, 
    source_row_number INTEGER NOT NULL, 
    original_dates_json NVARCHAR(max) NOT NULL, 
    pedimento_completo NVARCHAR(450) NULL, 
    patente NVARCHAR(max) NULL, 
    pedimento NVARCHAR(max) NULL, 
    seccion_aduanera NVARCHAR(max) NULL, 
    tipo_fecha NVARCHAR(max) NULL, 
    fecha_operacion DATETIME2 NULL, 
    fecha_validacion_pago_r DATETIME2 NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(period_id) REFERENCES periods (id), 
    FOREIGN KEY(processing_file_id) REFERENCES processing_files (id), 
    FOREIGN KEY(processing_run_id) REFERENCES processing_runs (id), 
    CONSTRAINT uq_ds_506_source UNIQUE (processing_run_id, processing_file_id, source_row_number)
);

GO

CREATE INDEX ix_ds_506_pedimento ON ds_506 (pedimento_completo);

GO

CREATE INDEX ix_ds_506_period ON ds_506 (period_id);

GO

CREATE INDEX ix_ds_506_run ON ds_506 (processing_run_id);

GO

CREATE TABLE ds_507 (
    id BIGINT NOT NULL IDENTITY, 
    period_id VARCHAR(36) NOT NULL, 
    processing_run_id VARCHAR(36) NOT NULL, 
    processing_file_id VARCHAR(36) NOT NULL, 
    archivo_origen NVARCHAR(512) NOT NULL, 
    folio_origen NVARCHAR(512) NOT NULL, 
    table_code NVARCHAR(100) NOT NULL, 
    ingested_at DATETIME2 NOT NULL, 
    source_row_number INTEGER NOT NULL, 
    original_dates_json NVARCHAR(max) NOT NULL, 
    pedimento_completo NVARCHAR(450) NULL, 
    patente NVARCHAR(max) NULL, 
    pedimento NVARCHAR(max) NULL, 
    seccion_aduanera NVARCHAR(max) NULL, 
    clave_caso NVARCHAR(max) NULL, 
    identificador_caso NVARCHAR(max) NULL, 
    tipo_pedimento NVARCHAR(max) NULL, 
    complemento_caso NVARCHAR(max) NULL, 
    fecha_validacion_pago_r DATETIME2 NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(period_id) REFERENCES periods (id), 
    FOREIGN KEY(processing_file_id) REFERENCES processing_files (id), 
    FOREIGN KEY(processing_run_id) REFERENCES processing_runs (id), 
    CONSTRAINT uq_ds_507_source UNIQUE (processing_run_id, processing_file_id, source_row_number)
);

GO

CREATE INDEX ix_ds_507_pedimento ON ds_507 (pedimento_completo);

GO

CREATE INDEX ix_ds_507_period ON ds_507 (period_id);

GO

CREATE INDEX ix_ds_507_run ON ds_507 (processing_run_id);

GO

CREATE TABLE ds_508 (
    id BIGINT NOT NULL IDENTITY, 
    period_id VARCHAR(36) NOT NULL, 
    processing_run_id VARCHAR(36) NOT NULL, 
    processing_file_id VARCHAR(36) NOT NULL, 
    archivo_origen NVARCHAR(512) NOT NULL, 
    folio_origen NVARCHAR(512) NOT NULL, 
    table_code NVARCHAR(100) NOT NULL, 
    ingested_at DATETIME2 NOT NULL, 
    source_row_number INTEGER NOT NULL, 
    original_dates_json NVARCHAR(max) NOT NULL, 
    pedimento_completo NVARCHAR(450) NULL, 
    patente NVARCHAR(max) NULL, 
    pedimento NVARCHAR(max) NULL, 
    seccion_aduanera NVARCHAR(max) NULL, 
    institucion_emisora NVARCHAR(max) NULL, 
    numero_cuenta NVARCHAR(max) NULL, 
    folio_constancia NVARCHAR(max) NULL, 
    fecha_constancia DATETIME2 NULL, 
    tipo_cuenta NVARCHAR(max) NULL, 
    clave_garantia NVARCHAR(max) NULL, 
    valor_unitario_titulo NVARCHAR(max) NULL, 
    total_garantia NVARCHAR(max) NULL, 
    cantidad_unidades NVARCHAR(max) NULL, 
    titulos_asignados NVARCHAR(max) NULL, 
    fecha_pago_real DATETIME2 NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(period_id) REFERENCES periods (id), 
    FOREIGN KEY(processing_file_id) REFERENCES processing_files (id), 
    FOREIGN KEY(processing_run_id) REFERENCES processing_runs (id), 
    CONSTRAINT uq_ds_508_source UNIQUE (processing_run_id, processing_file_id, source_row_number)
);

GO

CREATE INDEX ix_ds_508_pedimento ON ds_508 (pedimento_completo);

GO

CREATE INDEX ix_ds_508_period ON ds_508 (period_id);

GO

CREATE INDEX ix_ds_508_run ON ds_508 (processing_run_id);

GO

CREATE TABLE ds_509 (
    id BIGINT NOT NULL IDENTITY, 
    period_id VARCHAR(36) NOT NULL, 
    processing_run_id VARCHAR(36) NOT NULL, 
    processing_file_id VARCHAR(36) NOT NULL, 
    archivo_origen NVARCHAR(512) NOT NULL, 
    folio_origen NVARCHAR(512) NOT NULL, 
    table_code NVARCHAR(100) NOT NULL, 
    ingested_at DATETIME2 NOT NULL, 
    source_row_number INTEGER NOT NULL, 
    original_dates_json NVARCHAR(max) NOT NULL, 
    pedimento_completo NVARCHAR(450) NULL, 
    patente NVARCHAR(max) NULL, 
    pedimento NVARCHAR(max) NULL, 
    seccion_aduanera NVARCHAR(max) NULL, 
    clave_contribucion NVARCHAR(max) NULL, 
    tasa_contribucion NVARCHAR(max) NULL, 
    tipo_tasa NVARCHAR(max) NULL, 
    tipo_pedimento NVARCHAR(max) NULL, 
    fecha_pago_real DATETIME2 NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(period_id) REFERENCES periods (id), 
    FOREIGN KEY(processing_file_id) REFERENCES processing_files (id), 
    FOREIGN KEY(processing_run_id) REFERENCES processing_runs (id), 
    CONSTRAINT uq_ds_509_source UNIQUE (processing_run_id, processing_file_id, source_row_number)
);

GO

CREATE INDEX ix_ds_509_pedimento ON ds_509 (pedimento_completo);

GO

CREATE INDEX ix_ds_509_period ON ds_509 (period_id);

GO

CREATE INDEX ix_ds_509_run ON ds_509 (processing_run_id);

GO

CREATE TABLE ds_510 (
    id BIGINT NOT NULL IDENTITY, 
    period_id VARCHAR(36) NOT NULL, 
    processing_run_id VARCHAR(36) NOT NULL, 
    processing_file_id VARCHAR(36) NOT NULL, 
    archivo_origen NVARCHAR(512) NOT NULL, 
    folio_origen NVARCHAR(512) NOT NULL, 
    table_code NVARCHAR(100) NOT NULL, 
    ingested_at DATETIME2 NOT NULL, 
    source_row_number INTEGER NOT NULL, 
    original_dates_json NVARCHAR(max) NOT NULL, 
    pedimento_completo NVARCHAR(450) NULL, 
    patente NVARCHAR(max) NULL, 
    pedimento NVARCHAR(max) NULL, 
    seccion_aduanera NVARCHAR(max) NULL, 
    clave_contribucion NVARCHAR(max) NULL, 
    forma_pago NVARCHAR(max) NULL, 
    importe_pago NVARCHAR(max) NULL, 
    tipo_pedimento NVARCHAR(max) NULL, 
    fecha_pago_real DATETIME2 NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(period_id) REFERENCES periods (id), 
    FOREIGN KEY(processing_file_id) REFERENCES processing_files (id), 
    FOREIGN KEY(processing_run_id) REFERENCES processing_runs (id), 
    CONSTRAINT uq_ds_510_source UNIQUE (processing_run_id, processing_file_id, source_row_number)
);

GO

CREATE INDEX ix_ds_510_pedimento ON ds_510 (pedimento_completo);

GO

CREATE INDEX ix_ds_510_period ON ds_510 (period_id);

GO

CREATE INDEX ix_ds_510_run ON ds_510 (processing_run_id);

GO

CREATE TABLE ds_511 (
    id BIGINT NOT NULL IDENTITY, 
    period_id VARCHAR(36) NOT NULL, 
    processing_run_id VARCHAR(36) NOT NULL, 
    processing_file_id VARCHAR(36) NOT NULL, 
    archivo_origen NVARCHAR(512) NOT NULL, 
    folio_origen NVARCHAR(512) NOT NULL, 
    table_code NVARCHAR(100) NOT NULL, 
    ingested_at DATETIME2 NOT NULL, 
    source_row_number INTEGER NOT NULL, 
    original_dates_json NVARCHAR(max) NOT NULL, 
    pedimento_completo NVARCHAR(450) NULL, 
    patente NVARCHAR(max) NULL, 
    pedimento NVARCHAR(max) NULL, 
    seccion_aduanera NVARCHAR(max) NULL, 
    secuencia_observacion NVARCHAR(max) NULL, 
    observaciones NVARCHAR(max) NULL, 
    tipo_pedimento NVARCHAR(max) NULL, 
    fecha_validacion_pago_r DATETIME2 NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(period_id) REFERENCES periods (id), 
    FOREIGN KEY(processing_file_id) REFERENCES processing_files (id), 
    FOREIGN KEY(processing_run_id) REFERENCES processing_runs (id), 
    CONSTRAINT uq_ds_511_source UNIQUE (processing_run_id, processing_file_id, source_row_number)
);

GO

CREATE INDEX ix_ds_511_pedimento ON ds_511 (pedimento_completo);

GO

CREATE INDEX ix_ds_511_period ON ds_511 (period_id);

GO

CREATE INDEX ix_ds_511_run ON ds_511 (processing_run_id);

GO

CREATE TABLE ds_512 (
    id BIGINT NOT NULL IDENTITY, 
    period_id VARCHAR(36) NOT NULL, 
    processing_run_id VARCHAR(36) NOT NULL, 
    processing_file_id VARCHAR(36) NOT NULL, 
    archivo_origen NVARCHAR(512) NOT NULL, 
    folio_origen NVARCHAR(512) NOT NULL, 
    table_code NVARCHAR(100) NOT NULL, 
    ingested_at DATETIME2 NOT NULL, 
    source_row_number INTEGER NOT NULL, 
    original_dates_json NVARCHAR(max) NOT NULL, 
    pedimento_completo NVARCHAR(450) NULL, 
    patente NVARCHAR(max) NULL, 
    pedimento NVARCHAR(max) NULL, 
    seccion_aduanera NVARCHAR(max) NULL, 
    patente_aduanal_orig NVARCHAR(max) NULL, 
    pedimento_original NVARCHAR(max) NULL, 
    seccion_aduanera_desp_orig NVARCHAR(max) NULL, 
    documento_original NVARCHAR(max) NULL, 
    fecha_operacion_orig DATETIME2 NULL, 
    fraccion_original NVARCHAR(max) NULL, 
    unidad_medida NVARCHAR(max) NULL, 
    mercancia_descargada NVARCHAR(max) NULL, 
    tipo_pedimento NVARCHAR(max) NULL, 
    fecha_pago_real DATETIME2 NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(period_id) REFERENCES periods (id), 
    FOREIGN KEY(processing_file_id) REFERENCES processing_files (id), 
    FOREIGN KEY(processing_run_id) REFERENCES processing_runs (id), 
    CONSTRAINT uq_ds_512_source UNIQUE (processing_run_id, processing_file_id, source_row_number)
);

GO

CREATE INDEX ix_ds_512_pedimento ON ds_512 (pedimento_completo);

GO

CREATE INDEX ix_ds_512_period ON ds_512 (period_id);

GO

CREATE INDEX ix_ds_512_run ON ds_512 (processing_run_id);

GO

CREATE TABLE ds_520 (
    id BIGINT NOT NULL IDENTITY, 
    period_id VARCHAR(36) NOT NULL, 
    processing_run_id VARCHAR(36) NOT NULL, 
    processing_file_id VARCHAR(36) NOT NULL, 
    archivo_origen NVARCHAR(512) NOT NULL, 
    folio_origen NVARCHAR(512) NOT NULL, 
    table_code NVARCHAR(100) NOT NULL, 
    ingested_at DATETIME2 NOT NULL, 
    source_row_number INTEGER NOT NULL, 
    original_dates_json NVARCHAR(max) NOT NULL, 
    pedimento_completo NVARCHAR(450) NULL, 
    patente NVARCHAR(max) NULL, 
    pedimento NVARCHAR(max) NULL, 
    seccion_aduanera NVARCHAR(max) NULL, 
    indent_fiscal_destinatario NVARCHAR(max) NULL, 
    nombre_destinatario_mercancia NVARCHAR(max) NULL, 
    calle_destinatario NVARCHAR(max) NULL, 
    num_interior_destinatario NVARCHAR(max) NULL, 
    num_exterior_destinatario NVARCHAR(max) NULL, 
    cp_destinatario NVARCHAR(max) NULL, 
    municpio_destinatario NVARCHAR(max) NULL, 
    pais_destinatario NVARCHAR(max) NULL, 
    fecha_pago_real DATETIME2 NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(period_id) REFERENCES periods (id), 
    FOREIGN KEY(processing_file_id) REFERENCES processing_files (id), 
    FOREIGN KEY(processing_run_id) REFERENCES processing_runs (id), 
    CONSTRAINT uq_ds_520_source UNIQUE (processing_run_id, processing_file_id, source_row_number)
);

GO

CREATE INDEX ix_ds_520_pedimento ON ds_520 (pedimento_completo);

GO

CREATE INDEX ix_ds_520_period ON ds_520 (period_id);

GO

CREATE INDEX ix_ds_520_run ON ds_520 (processing_run_id);

GO

CREATE TABLE ds_551 (
    id BIGINT NOT NULL IDENTITY, 
    period_id VARCHAR(36) NOT NULL, 
    processing_run_id VARCHAR(36) NOT NULL, 
    processing_file_id VARCHAR(36) NOT NULL, 
    archivo_origen NVARCHAR(512) NOT NULL, 
    folio_origen NVARCHAR(512) NOT NULL, 
    table_code NVARCHAR(100) NOT NULL, 
    ingested_at DATETIME2 NOT NULL, 
    source_row_number INTEGER NOT NULL, 
    original_dates_json NVARCHAR(max) NOT NULL, 
    pedimento_completo NVARCHAR(450) NULL, 
    patente NVARCHAR(max) NULL, 
    pedimento NVARCHAR(max) NULL, 
    seccion_aduanera NVARCHAR(max) NULL, 
    fraccion NVARCHAR(max) NULL, 
    secuencia_fraccion NVARCHAR(max) NULL, 
    subdivision_fraccion NVARCHAR(max) NULL, 
    descripcion_mercancia NVARCHAR(max) NULL, 
    precio_unitario NVARCHAR(max) NULL, 
    valor_aduana NVARCHAR(max) NULL, 
    valor_comercial NVARCHAR(max) NULL, 
    valor_dolares NVARCHAR(max) NULL, 
    cantidad_um_comercial NVARCHAR(max) NULL, 
    unidad_medida_comercial NVARCHAR(max) NULL, 
    cantidad_um_tarifa NVARCHAR(max) NULL, 
    unidad_medida_tarifa NVARCHAR(max) NULL, 
    valor_agregado NVARCHAR(max) NULL, 
    clave_vinculacion NVARCHAR(max) NULL, 
    metodo_valorizacion NVARCHAR(max) NULL, 
    codigo_mercancia_producto NVARCHAR(max) NULL, 
    marca_mercancia_producto NVARCHAR(max) NULL, 
    modelo_mercancia_producto NVARCHAR(max) NULL, 
    pais_origen_destino NVARCHAR(max) NULL, 
    pais_comprador_vendedor NVARCHAR(max) NULL, 
    entidad_fed_origen NVARCHAR(max) NULL, 
    entidad_fed_destino NVARCHAR(max) NULL, 
    entidad_fed_comprador NVARCHAR(max) NULL, 
    entidad_fed_vendedor NVARCHAR(max) NULL, 
    tipo_operacion NVARCHAR(max) NULL, 
    clave_documento NVARCHAR(max) NULL, 
    fecha_pago_real DATETIME2 NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(period_id) REFERENCES periods (id), 
    FOREIGN KEY(processing_file_id) REFERENCES processing_files (id), 
    FOREIGN KEY(processing_run_id) REFERENCES processing_runs (id), 
    CONSTRAINT uq_ds_551_source UNIQUE (processing_run_id, processing_file_id, source_row_number)
);

GO

CREATE INDEX ix_ds_551_pedimento ON ds_551 (pedimento_completo);

GO

CREATE INDEX ix_ds_551_period ON ds_551 (period_id);

GO

CREATE INDEX ix_ds_551_run ON ds_551 (processing_run_id);

GO

CREATE TABLE ds_552 (
    id BIGINT NOT NULL IDENTITY, 
    period_id VARCHAR(36) NOT NULL, 
    processing_run_id VARCHAR(36) NOT NULL, 
    processing_file_id VARCHAR(36) NOT NULL, 
    archivo_origen NVARCHAR(512) NOT NULL, 
    folio_origen NVARCHAR(512) NOT NULL, 
    table_code NVARCHAR(100) NOT NULL, 
    ingested_at DATETIME2 NOT NULL, 
    source_row_number INTEGER NOT NULL, 
    original_dates_json NVARCHAR(max) NOT NULL, 
    pedimento_completo NVARCHAR(450) NULL, 
    patente NVARCHAR(max) NULL, 
    pedimento NVARCHAR(max) NULL, 
    seccion_aduanera NVARCHAR(max) NULL, 
    fraccion NVARCHAR(max) NULL, 
    secuencia_fraccion NVARCHAR(max) NULL, 
    vin_numero_serie NVARCHAR(max) NULL, 
    kilometraje_vehiculo NVARCHAR(max) NULL, 
    fecha_pago_real DATETIME2 NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(period_id) REFERENCES periods (id), 
    FOREIGN KEY(processing_file_id) REFERENCES processing_files (id), 
    FOREIGN KEY(processing_run_id) REFERENCES processing_runs (id), 
    CONSTRAINT uq_ds_552_source UNIQUE (processing_run_id, processing_file_id, source_row_number)
);

GO

CREATE INDEX ix_ds_552_pedimento ON ds_552 (pedimento_completo);

GO

CREATE INDEX ix_ds_552_period ON ds_552 (period_id);

GO

CREATE INDEX ix_ds_552_run ON ds_552 (processing_run_id);

GO

CREATE TABLE ds_553 (
    id BIGINT NOT NULL IDENTITY, 
    period_id VARCHAR(36) NOT NULL, 
    processing_run_id VARCHAR(36) NOT NULL, 
    processing_file_id VARCHAR(36) NOT NULL, 
    archivo_origen NVARCHAR(512) NOT NULL, 
    folio_origen NVARCHAR(512) NOT NULL, 
    table_code NVARCHAR(100) NOT NULL, 
    ingested_at DATETIME2 NOT NULL, 
    source_row_number INTEGER NOT NULL, 
    original_dates_json NVARCHAR(max) NOT NULL, 
    pedimento_completo NVARCHAR(450) NULL, 
    patente NVARCHAR(max) NULL, 
    pedimento NVARCHAR(max) NULL, 
    seccion_aduanera NVARCHAR(max) NULL, 
    fraccion NVARCHAR(max) NULL, 
    secuencia_fraccion NVARCHAR(max) NULL, 
    clave_permiso NVARCHAR(max) NULL, 
    firma_descargo NVARCHAR(max) NULL, 
    numero_permiso NVARCHAR(max) NULL, 
    valor_comercial_dolares NVARCHAR(max) NULL, 
    cantidad_mum_tarifa NVARCHAR(max) NULL, 
    fecha_pago_real DATETIME2 NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(period_id) REFERENCES periods (id), 
    FOREIGN KEY(processing_file_id) REFERENCES processing_files (id), 
    FOREIGN KEY(processing_run_id) REFERENCES processing_runs (id), 
    CONSTRAINT uq_ds_553_source UNIQUE (processing_run_id, processing_file_id, source_row_number)
);

GO

CREATE INDEX ix_ds_553_pedimento ON ds_553 (pedimento_completo);

GO

CREATE INDEX ix_ds_553_period ON ds_553 (period_id);

GO

CREATE INDEX ix_ds_553_run ON ds_553 (processing_run_id);

GO

CREATE TABLE ds_554 (
    id BIGINT NOT NULL IDENTITY, 
    period_id VARCHAR(36) NOT NULL, 
    processing_run_id VARCHAR(36) NOT NULL, 
    processing_file_id VARCHAR(36) NOT NULL, 
    archivo_origen NVARCHAR(512) NOT NULL, 
    folio_origen NVARCHAR(512) NOT NULL, 
    table_code NVARCHAR(100) NOT NULL, 
    ingested_at DATETIME2 NOT NULL, 
    source_row_number INTEGER NOT NULL, 
    original_dates_json NVARCHAR(max) NOT NULL, 
    pedimento_completo NVARCHAR(450) NULL, 
    patente NVARCHAR(max) NULL, 
    pedimento NVARCHAR(max) NULL, 
    seccion_aduanera NVARCHAR(max) NULL, 
    fraccion NVARCHAR(max) NULL, 
    secuencia_fraccion NVARCHAR(max) NULL, 
    clave_caso NVARCHAR(max) NULL, 
    identificador_caso NVARCHAR(max) NULL, 
    complemento_caso NVARCHAR(max) NULL, 
    fecha_pago_real DATETIME2 NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(period_id) REFERENCES periods (id), 
    FOREIGN KEY(processing_file_id) REFERENCES processing_files (id), 
    FOREIGN KEY(processing_run_id) REFERENCES processing_runs (id), 
    CONSTRAINT uq_ds_554_source UNIQUE (processing_run_id, processing_file_id, source_row_number)
);

GO

CREATE INDEX ix_ds_554_pedimento ON ds_554 (pedimento_completo);

GO

CREATE INDEX ix_ds_554_period ON ds_554 (period_id);

GO

CREATE INDEX ix_ds_554_run ON ds_554 (processing_run_id);

GO

CREATE TABLE ds_555 (
    id BIGINT NOT NULL IDENTITY, 
    period_id VARCHAR(36) NOT NULL, 
    processing_run_id VARCHAR(36) NOT NULL, 
    processing_file_id VARCHAR(36) NOT NULL, 
    archivo_origen NVARCHAR(512) NOT NULL, 
    folio_origen NVARCHAR(512) NOT NULL, 
    table_code NVARCHAR(100) NOT NULL, 
    ingested_at DATETIME2 NOT NULL, 
    source_row_number INTEGER NOT NULL, 
    original_dates_json NVARCHAR(max) NOT NULL, 
    pedimento_completo NVARCHAR(450) NULL, 
    patente NVARCHAR(max) NULL, 
    pedimento NVARCHAR(max) NULL, 
    seccion_aduanera NVARCHAR(max) NULL, 
    fraccion NVARCHAR(max) NULL, 
    secuencia_fraccion NVARCHAR(max) NULL, 
    institucion_emisora NVARCHAR(max) NULL, 
    numero_cuenta NVARCHAR(max) NULL, 
    folio_constancia NVARCHAR(max) NULL, 
    fecha_constancia DATETIME2 NULL, 
    clave_garantia NVARCHAR(max) NULL, 
    valor_unitario_titulo NVARCHAR(max) NULL, 
    total_garantia NVARCHAR(max) NULL, 
    cantidad_unidades_medida NVARCHAR(max) NULL, 
    titulos_asignados NVARCHAR(max) NULL, 
    fecha_pago_real DATETIME2 NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(period_id) REFERENCES periods (id), 
    FOREIGN KEY(processing_file_id) REFERENCES processing_files (id), 
    FOREIGN KEY(processing_run_id) REFERENCES processing_runs (id), 
    CONSTRAINT uq_ds_555_source UNIQUE (processing_run_id, processing_file_id, source_row_number)
);

GO

CREATE INDEX ix_ds_555_pedimento ON ds_555 (pedimento_completo);

GO

CREATE INDEX ix_ds_555_period ON ds_555 (period_id);

GO

CREATE INDEX ix_ds_555_run ON ds_555 (processing_run_id);

GO

CREATE TABLE ds_556 (
    id BIGINT NOT NULL IDENTITY, 
    period_id VARCHAR(36) NOT NULL, 
    processing_run_id VARCHAR(36) NOT NULL, 
    processing_file_id VARCHAR(36) NOT NULL, 
    archivo_origen NVARCHAR(512) NOT NULL, 
    folio_origen NVARCHAR(512) NOT NULL, 
    table_code NVARCHAR(100) NOT NULL, 
    ingested_at DATETIME2 NOT NULL, 
    source_row_number INTEGER NOT NULL, 
    original_dates_json NVARCHAR(max) NOT NULL, 
    pedimento_completo NVARCHAR(450) NULL, 
    patente NVARCHAR(max) NULL, 
    pedimento NVARCHAR(max) NULL, 
    seccion_aduanera NVARCHAR(max) NULL, 
    fraccion NVARCHAR(max) NULL, 
    secuencia_fraccion NVARCHAR(max) NULL, 
    clave_contribucion NVARCHAR(max) NULL, 
    tasa_contribucion NVARCHAR(max) NULL, 
    tipo_tasa NVARCHAR(max) NULL, 
    fecha_pago_real DATETIME2 NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(period_id) REFERENCES periods (id), 
    FOREIGN KEY(processing_file_id) REFERENCES processing_files (id), 
    FOREIGN KEY(processing_run_id) REFERENCES processing_runs (id), 
    CONSTRAINT uq_ds_556_source UNIQUE (processing_run_id, processing_file_id, source_row_number)
);

GO

CREATE INDEX ix_ds_556_pedimento ON ds_556 (pedimento_completo);

GO

CREATE INDEX ix_ds_556_period ON ds_556 (period_id);

GO

CREATE INDEX ix_ds_556_run ON ds_556 (processing_run_id);

GO

CREATE TABLE ds_557 (
    id BIGINT NOT NULL IDENTITY, 
    period_id VARCHAR(36) NOT NULL, 
    processing_run_id VARCHAR(36) NOT NULL, 
    processing_file_id VARCHAR(36) NOT NULL, 
    archivo_origen NVARCHAR(512) NOT NULL, 
    folio_origen NVARCHAR(512) NOT NULL, 
    table_code NVARCHAR(100) NOT NULL, 
    ingested_at DATETIME2 NOT NULL, 
    source_row_number INTEGER NOT NULL, 
    original_dates_json NVARCHAR(max) NOT NULL, 
    pedimento_completo NVARCHAR(450) NULL, 
    patente NVARCHAR(max) NULL, 
    pedimento NVARCHAR(max) NULL, 
    seccion_aduanera NVARCHAR(max) NULL, 
    fraccion NVARCHAR(max) NULL, 
    secuencia_fraccion NVARCHAR(max) NULL, 
    clave_contribucion NVARCHAR(max) NULL, 
    forma_pago NVARCHAR(max) NULL, 
    importe_pago NVARCHAR(max) NULL, 
    fecha_pago_real DATETIME2 NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(period_id) REFERENCES periods (id), 
    FOREIGN KEY(processing_file_id) REFERENCES processing_files (id), 
    FOREIGN KEY(processing_run_id) REFERENCES processing_runs (id), 
    CONSTRAINT uq_ds_557_source UNIQUE (processing_run_id, processing_file_id, source_row_number)
);

GO

CREATE INDEX ix_ds_557_pedimento ON ds_557 (pedimento_completo);

GO

CREATE INDEX ix_ds_557_period ON ds_557 (period_id);

GO

CREATE INDEX ix_ds_557_run ON ds_557 (processing_run_id);

GO

CREATE TABLE ds_558 (
    id BIGINT NOT NULL IDENTITY, 
    period_id VARCHAR(36) NOT NULL, 
    processing_run_id VARCHAR(36) NOT NULL, 
    processing_file_id VARCHAR(36) NOT NULL, 
    archivo_origen NVARCHAR(512) NOT NULL, 
    folio_origen NVARCHAR(512) NOT NULL, 
    table_code NVARCHAR(100) NOT NULL, 
    ingested_at DATETIME2 NOT NULL, 
    source_row_number INTEGER NOT NULL, 
    original_dates_json NVARCHAR(max) NOT NULL, 
    pedimento_completo NVARCHAR(450) NULL, 
    patente NVARCHAR(max) NULL, 
    pedimento NVARCHAR(max) NULL, 
    seccion_aduanera NVARCHAR(max) NULL, 
    fraccion NVARCHAR(max) NULL, 
    secuencia_fraccion NVARCHAR(max) NULL, 
    secuencia_observacion NVARCHAR(max) NULL, 
    observaciones NVARCHAR(max) NULL, 
    fecha_pago_real DATETIME2 NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(period_id) REFERENCES periods (id), 
    FOREIGN KEY(processing_file_id) REFERENCES processing_files (id), 
    FOREIGN KEY(processing_run_id) REFERENCES processing_runs (id), 
    CONSTRAINT uq_ds_558_source UNIQUE (processing_run_id, processing_file_id, source_row_number)
);

GO

CREATE INDEX ix_ds_558_pedimento ON ds_558 (pedimento_completo);

GO

CREATE INDEX ix_ds_558_period ON ds_558 (period_id);

GO

CREATE INDEX ix_ds_558_run ON ds_558 (processing_run_id);

GO

CREATE TABLE ds_701 (
    id BIGINT NOT NULL IDENTITY, 
    period_id VARCHAR(36) NOT NULL, 
    processing_run_id VARCHAR(36) NOT NULL, 
    processing_file_id VARCHAR(36) NOT NULL, 
    archivo_origen NVARCHAR(512) NOT NULL, 
    folio_origen NVARCHAR(512) NOT NULL, 
    table_code NVARCHAR(100) NOT NULL, 
    ingested_at DATETIME2 NOT NULL, 
    source_row_number INTEGER NOT NULL, 
    original_dates_json NVARCHAR(max) NOT NULL, 
    pedimento_completo NVARCHAR(450) NULL, 
    patente NVARCHAR(max) NULL, 
    pedimento NVARCHAR(max) NULL, 
    seccion_aduanera NVARCHAR(max) NULL, 
    clave_documento NVARCHAR(max) NULL, 
    fecha_pago DATETIME2 NULL, 
    pedimento_anterior NVARCHAR(max) NULL, 
    patente_anterior NVARCHAR(max) NULL, 
    seccion_aduanera_anterior NVARCHAR(max) NULL, 
    documento_anterior NVARCHAR(max) NULL, 
    fecha_operacion_anterior DATETIME2 NULL, 
    pedimento_original NVARCHAR(max) NULL, 
    patente_aduanal_orig NVARCHAR(max) NULL, 
    seccion_aduanera_desp_orig NVARCHAR(max) NULL, 
    fecha_pago_real DATETIME2 NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(period_id) REFERENCES periods (id), 
    FOREIGN KEY(processing_file_id) REFERENCES processing_files (id), 
    FOREIGN KEY(processing_run_id) REFERENCES processing_runs (id), 
    CONSTRAINT uq_ds_701_source UNIQUE (processing_run_id, processing_file_id, source_row_number)
);

GO

CREATE INDEX ix_ds_701_pedimento ON ds_701 (pedimento_completo);

GO

CREATE INDEX ix_ds_701_period ON ds_701 (period_id);

GO

CREATE INDEX ix_ds_701_run ON ds_701 (processing_run_id);

GO

CREATE TABLE ds_702 (
    id BIGINT NOT NULL IDENTITY, 
    period_id VARCHAR(36) NOT NULL, 
    processing_run_id VARCHAR(36) NOT NULL, 
    processing_file_id VARCHAR(36) NOT NULL, 
    archivo_origen NVARCHAR(512) NOT NULL, 
    folio_origen NVARCHAR(512) NOT NULL, 
    table_code NVARCHAR(100) NOT NULL, 
    ingested_at DATETIME2 NOT NULL, 
    source_row_number INTEGER NOT NULL, 
    original_dates_json NVARCHAR(max) NOT NULL, 
    pedimento_completo NVARCHAR(450) NULL, 
    patente NVARCHAR(max) NULL, 
    pedimento NVARCHAR(max) NULL, 
    seccion_aduanera NVARCHAR(max) NULL, 
    clave_contribucion NVARCHAR(max) NULL, 
    forma_pago NVARCHAR(max) NULL, 
    importe_pago NVARCHAR(max) NULL, 
    tipo_pedimento NVARCHAR(max) NULL, 
    fecha_pago_real DATETIME2 NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(period_id) REFERENCES periods (id), 
    FOREIGN KEY(processing_file_id) REFERENCES processing_files (id), 
    FOREIGN KEY(processing_run_id) REFERENCES processing_runs (id), 
    CONSTRAINT uq_ds_702_source UNIQUE (processing_run_id, processing_file_id, source_row_number)
);

GO

CREATE INDEX ix_ds_702_pedimento ON ds_702 (pedimento_completo);

GO

CREATE INDEX ix_ds_702_period ON ds_702 (period_id);

GO

CREATE INDEX ix_ds_702_run ON ds_702 (processing_run_id);

GO

CREATE TABLE ds_inci (
    id BIGINT NOT NULL IDENTITY, 
    period_id VARCHAR(36) NOT NULL, 
    processing_run_id VARCHAR(36) NOT NULL, 
    processing_file_id VARCHAR(36) NOT NULL, 
    archivo_origen NVARCHAR(512) NOT NULL, 
    folio_origen NVARCHAR(512) NOT NULL, 
    table_code NVARCHAR(100) NOT NULL, 
    ingested_at DATETIME2 NOT NULL, 
    source_row_number INTEGER NOT NULL, 
    original_dates_json NVARCHAR(max) NOT NULL, 
    pedimento_completo NVARCHAR(450) NULL, 
    patente NVARCHAR(max) NULL, 
    pedimento NVARCHAR(max) NULL, 
    seccion_aduanera NVARCHAR(max) NULL, 
    consecutivo_remesa NVARCHAR(max) NULL, 
    numero_seleccion NVARCHAR(max) NULL, 
    fecha_inicio_reconocimiento DATETIME2 NULL, 
    hora_inicio_reconocimiento NVARCHAR(max) NULL, 
    fecha_fin_reconocimiento DATETIME2 NULL, 
    hora_fin_reconocimiento NVARCHAR(max) NULL, 
    fraccion NVARCHAR(max) NULL, 
    secuencia_fraccion NVARCHAR(max) NULL, 
    clave_documento NVARCHAR(max) NULL, 
    tipo_operacion NVARCHAR(max) NULL, 
    grado_incidencia NVARCHAR(max) NULL, 
    fecha_seleccion DATETIME2 NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(period_id) REFERENCES periods (id), 
    FOREIGN KEY(processing_file_id) REFERENCES processing_files (id), 
    FOREIGN KEY(processing_run_id) REFERENCES processing_runs (id), 
    CONSTRAINT uq_ds_inci_source UNIQUE (processing_run_id, processing_file_id, source_row_number)
);

GO

CREATE INDEX ix_ds_inci_pedimento ON ds_inci (pedimento_completo);

GO

CREATE INDEX ix_ds_inci_period ON ds_inci (period_id);

GO

CREATE INDEX ix_ds_inci_run ON ds_inci (processing_run_id);

GO

CREATE TABLE ds_resumen (
    id BIGINT NOT NULL IDENTITY, 
    period_id VARCHAR(36) NOT NULL, 
    processing_run_id VARCHAR(36) NOT NULL, 
    processing_file_id VARCHAR(36) NOT NULL, 
    archivo_origen NVARCHAR(512) NOT NULL, 
    folio_origen NVARCHAR(512) NOT NULL, 
    table_code NVARCHAR(100) NOT NULL, 
    ingested_at DATETIME2 NOT NULL, 
    source_row_number INTEGER NOT NULL, 
    original_dates_json NVARCHAR(max) NOT NULL, 
    folio NVARCHAR(max) NULL, 
    rf_co_patente_aduanal NVARCHAR(max) NULL, 
    fecha_inicial DATETIME2 NULL, 
    fecha_final DATETIME2 NULL, 
    fecha_ejecucion DATETIME2 NULL, 
    total_fracciones NVARCHAR(max) NULL, 
    total_contribuciones NVARCHAR(max) NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(period_id) REFERENCES periods (id), 
    FOREIGN KEY(processing_file_id) REFERENCES processing_files (id), 
    FOREIGN KEY(processing_run_id) REFERENCES processing_runs (id), 
    CONSTRAINT uq_ds_resumen_source UNIQUE (processing_run_id, processing_file_id, source_row_number)
);

GO

CREATE INDEX ix_ds_resumen_period ON ds_resumen (period_id);

GO

CREATE INDEX ix_ds_resumen_run ON ds_resumen (processing_run_id);

GO

CREATE TABLE ds_sel (
    id BIGINT NOT NULL IDENTITY, 
    period_id VARCHAR(36) NOT NULL, 
    processing_run_id VARCHAR(36) NOT NULL, 
    processing_file_id VARCHAR(36) NOT NULL, 
    archivo_origen NVARCHAR(512) NOT NULL, 
    folio_origen NVARCHAR(512) NOT NULL, 
    table_code NVARCHAR(100) NOT NULL, 
    ingested_at DATETIME2 NOT NULL, 
    source_row_number INTEGER NOT NULL, 
    original_dates_json NVARCHAR(max) NOT NULL, 
    pedimento_completo NVARCHAR(450) NULL, 
    patente NVARCHAR(max) NULL, 
    pedimento NVARCHAR(max) NULL, 
    seccion_aduanera NVARCHAR(max) NULL, 
    consecutivo_remesa NVARCHAR(max) NULL, 
    numero_seleccion NVARCHAR(max) NULL, 
    fecha_seleccion DATETIME2 NULL, 
    hora_seleccion NVARCHAR(max) NULL, 
    semaforo_fiscal NVARCHAR(max) NULL, 
    clave_documento NVARCHAR(max) NULL, 
    tipo_operacion NVARCHAR(max) NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(period_id) REFERENCES periods (id), 
    FOREIGN KEY(processing_file_id) REFERENCES processing_files (id), 
    FOREIGN KEY(processing_run_id) REFERENCES processing_runs (id), 
    CONSTRAINT uq_ds_sel_source UNIQUE (processing_run_id, processing_file_id, source_row_number)
);

GO

CREATE INDEX ix_ds_sel_pedimento ON ds_sel (pedimento_completo);

GO

CREATE INDEX ix_ds_sel_period ON ds_sel (period_id);

GO

CREATE INDEX ix_ds_sel_run ON ds_sel (processing_run_id);

GO

CREATE TABLE processing_issues (
    run_id VARCHAR(36) NOT NULL, 
    file_id VARCHAR(36) NULL, 
    severity VARCHAR(10) NOT NULL, 
    code VARCHAR(100) NOT NULL, 
    message NVARCHAR(max) NOT NULL, 
    row_number INTEGER NULL, 
    column_name NVARCHAR(512) NULL, 
    original_value NVARCHAR(max) NULL, 
    id VARCHAR(36) NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_issue_severity CHECK (severity IN ('error', 'warning')), 
    FOREIGN KEY(file_id) REFERENCES processing_files (id), 
    FOREIGN KEY(run_id) REFERENCES processing_runs (id)
);

GO

CREATE INDEX ix_issues_run_severity ON processing_issues (run_id, severity);

GO

CREATE TABLE ds_501_extensions (
    id BIGINT NOT NULL IDENTITY, 
    business_row_id BIGINT NOT NULL, 
    header_key NVARCHAR(200) NOT NULL, 
    original_header NVARCHAR(512) NOT NULL, 
    original_value NVARCHAR(max) NOT NULL, 
    date_value DATETIME2 NULL, 
    value_kind VARCHAR(10) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(business_row_id) REFERENCES ds_501 (id), 
    CONSTRAINT uq_ds_501_extension_header UNIQUE (business_row_id, header_key)
);

GO

CREATE TABLE ds_502_extensions (
    id BIGINT NOT NULL IDENTITY, 
    business_row_id BIGINT NOT NULL, 
    header_key NVARCHAR(200) NOT NULL, 
    original_header NVARCHAR(512) NOT NULL, 
    original_value NVARCHAR(max) NOT NULL, 
    date_value DATETIME2 NULL, 
    value_kind VARCHAR(10) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(business_row_id) REFERENCES ds_502 (id), 
    CONSTRAINT uq_ds_502_extension_header UNIQUE (business_row_id, header_key)
);

GO

CREATE TABLE ds_503_extensions (
    id BIGINT NOT NULL IDENTITY, 
    business_row_id BIGINT NOT NULL, 
    header_key NVARCHAR(200) NOT NULL, 
    original_header NVARCHAR(512) NOT NULL, 
    original_value NVARCHAR(max) NOT NULL, 
    date_value DATETIME2 NULL, 
    value_kind VARCHAR(10) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(business_row_id) REFERENCES ds_503 (id), 
    CONSTRAINT uq_ds_503_extension_header UNIQUE (business_row_id, header_key)
);

GO

CREATE TABLE ds_504_extensions (
    id BIGINT NOT NULL IDENTITY, 
    business_row_id BIGINT NOT NULL, 
    header_key NVARCHAR(200) NOT NULL, 
    original_header NVARCHAR(512) NOT NULL, 
    original_value NVARCHAR(max) NOT NULL, 
    date_value DATETIME2 NULL, 
    value_kind VARCHAR(10) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(business_row_id) REFERENCES ds_504 (id), 
    CONSTRAINT uq_ds_504_extension_header UNIQUE (business_row_id, header_key)
);

GO

CREATE TABLE ds_505_extensions (
    id BIGINT NOT NULL IDENTITY, 
    business_row_id BIGINT NOT NULL, 
    header_key NVARCHAR(200) NOT NULL, 
    original_header NVARCHAR(512) NOT NULL, 
    original_value NVARCHAR(max) NOT NULL, 
    date_value DATETIME2 NULL, 
    value_kind VARCHAR(10) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(business_row_id) REFERENCES ds_505 (id), 
    CONSTRAINT uq_ds_505_extension_header UNIQUE (business_row_id, header_key)
);

GO

CREATE TABLE ds_506_extensions (
    id BIGINT NOT NULL IDENTITY, 
    business_row_id BIGINT NOT NULL, 
    header_key NVARCHAR(200) NOT NULL, 
    original_header NVARCHAR(512) NOT NULL, 
    original_value NVARCHAR(max) NOT NULL, 
    date_value DATETIME2 NULL, 
    value_kind VARCHAR(10) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(business_row_id) REFERENCES ds_506 (id), 
    CONSTRAINT uq_ds_506_extension_header UNIQUE (business_row_id, header_key)
);

GO

CREATE TABLE ds_507_extensions (
    id BIGINT NOT NULL IDENTITY, 
    business_row_id BIGINT NOT NULL, 
    header_key NVARCHAR(200) NOT NULL, 
    original_header NVARCHAR(512) NOT NULL, 
    original_value NVARCHAR(max) NOT NULL, 
    date_value DATETIME2 NULL, 
    value_kind VARCHAR(10) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(business_row_id) REFERENCES ds_507 (id), 
    CONSTRAINT uq_ds_507_extension_header UNIQUE (business_row_id, header_key)
);

GO

CREATE TABLE ds_508_extensions (
    id BIGINT NOT NULL IDENTITY, 
    business_row_id BIGINT NOT NULL, 
    header_key NVARCHAR(200) NOT NULL, 
    original_header NVARCHAR(512) NOT NULL, 
    original_value NVARCHAR(max) NOT NULL, 
    date_value DATETIME2 NULL, 
    value_kind VARCHAR(10) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(business_row_id) REFERENCES ds_508 (id), 
    CONSTRAINT uq_ds_508_extension_header UNIQUE (business_row_id, header_key)
);

GO

CREATE TABLE ds_509_extensions (
    id BIGINT NOT NULL IDENTITY, 
    business_row_id BIGINT NOT NULL, 
    header_key NVARCHAR(200) NOT NULL, 
    original_header NVARCHAR(512) NOT NULL, 
    original_value NVARCHAR(max) NOT NULL, 
    date_value DATETIME2 NULL, 
    value_kind VARCHAR(10) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(business_row_id) REFERENCES ds_509 (id), 
    CONSTRAINT uq_ds_509_extension_header UNIQUE (business_row_id, header_key)
);

GO

CREATE TABLE ds_510_extensions (
    id BIGINT NOT NULL IDENTITY, 
    business_row_id BIGINT NOT NULL, 
    header_key NVARCHAR(200) NOT NULL, 
    original_header NVARCHAR(512) NOT NULL, 
    original_value NVARCHAR(max) NOT NULL, 
    date_value DATETIME2 NULL, 
    value_kind VARCHAR(10) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(business_row_id) REFERENCES ds_510 (id), 
    CONSTRAINT uq_ds_510_extension_header UNIQUE (business_row_id, header_key)
);

GO

CREATE TABLE ds_511_extensions (
    id BIGINT NOT NULL IDENTITY, 
    business_row_id BIGINT NOT NULL, 
    header_key NVARCHAR(200) NOT NULL, 
    original_header NVARCHAR(512) NOT NULL, 
    original_value NVARCHAR(max) NOT NULL, 
    date_value DATETIME2 NULL, 
    value_kind VARCHAR(10) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(business_row_id) REFERENCES ds_511 (id), 
    CONSTRAINT uq_ds_511_extension_header UNIQUE (business_row_id, header_key)
);

GO

CREATE TABLE ds_512_extensions (
    id BIGINT NOT NULL IDENTITY, 
    business_row_id BIGINT NOT NULL, 
    header_key NVARCHAR(200) NOT NULL, 
    original_header NVARCHAR(512) NOT NULL, 
    original_value NVARCHAR(max) NOT NULL, 
    date_value DATETIME2 NULL, 
    value_kind VARCHAR(10) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(business_row_id) REFERENCES ds_512 (id), 
    CONSTRAINT uq_ds_512_extension_header UNIQUE (business_row_id, header_key)
);

GO

CREATE TABLE ds_520_extensions (
    id BIGINT NOT NULL IDENTITY, 
    business_row_id BIGINT NOT NULL, 
    header_key NVARCHAR(200) NOT NULL, 
    original_header NVARCHAR(512) NOT NULL, 
    original_value NVARCHAR(max) NOT NULL, 
    date_value DATETIME2 NULL, 
    value_kind VARCHAR(10) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(business_row_id) REFERENCES ds_520 (id), 
    CONSTRAINT uq_ds_520_extension_header UNIQUE (business_row_id, header_key)
);

GO

CREATE TABLE ds_551_extensions (
    id BIGINT NOT NULL IDENTITY, 
    business_row_id BIGINT NOT NULL, 
    header_key NVARCHAR(200) NOT NULL, 
    original_header NVARCHAR(512) NOT NULL, 
    original_value NVARCHAR(max) NOT NULL, 
    date_value DATETIME2 NULL, 
    value_kind VARCHAR(10) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(business_row_id) REFERENCES ds_551 (id), 
    CONSTRAINT uq_ds_551_extension_header UNIQUE (business_row_id, header_key)
);

GO

CREATE TABLE ds_552_extensions (
    id BIGINT NOT NULL IDENTITY, 
    business_row_id BIGINT NOT NULL, 
    header_key NVARCHAR(200) NOT NULL, 
    original_header NVARCHAR(512) NOT NULL, 
    original_value NVARCHAR(max) NOT NULL, 
    date_value DATETIME2 NULL, 
    value_kind VARCHAR(10) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(business_row_id) REFERENCES ds_552 (id), 
    CONSTRAINT uq_ds_552_extension_header UNIQUE (business_row_id, header_key)
);

GO

CREATE TABLE ds_553_extensions (
    id BIGINT NOT NULL IDENTITY, 
    business_row_id BIGINT NOT NULL, 
    header_key NVARCHAR(200) NOT NULL, 
    original_header NVARCHAR(512) NOT NULL, 
    original_value NVARCHAR(max) NOT NULL, 
    date_value DATETIME2 NULL, 
    value_kind VARCHAR(10) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(business_row_id) REFERENCES ds_553 (id), 
    CONSTRAINT uq_ds_553_extension_header UNIQUE (business_row_id, header_key)
);

GO

CREATE TABLE ds_554_extensions (
    id BIGINT NOT NULL IDENTITY, 
    business_row_id BIGINT NOT NULL, 
    header_key NVARCHAR(200) NOT NULL, 
    original_header NVARCHAR(512) NOT NULL, 
    original_value NVARCHAR(max) NOT NULL, 
    date_value DATETIME2 NULL, 
    value_kind VARCHAR(10) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(business_row_id) REFERENCES ds_554 (id), 
    CONSTRAINT uq_ds_554_extension_header UNIQUE (business_row_id, header_key)
);

GO

CREATE TABLE ds_555_extensions (
    id BIGINT NOT NULL IDENTITY, 
    business_row_id BIGINT NOT NULL, 
    header_key NVARCHAR(200) NOT NULL, 
    original_header NVARCHAR(512) NOT NULL, 
    original_value NVARCHAR(max) NOT NULL, 
    date_value DATETIME2 NULL, 
    value_kind VARCHAR(10) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(business_row_id) REFERENCES ds_555 (id), 
    CONSTRAINT uq_ds_555_extension_header UNIQUE (business_row_id, header_key)
);

GO

CREATE TABLE ds_556_extensions (
    id BIGINT NOT NULL IDENTITY, 
    business_row_id BIGINT NOT NULL, 
    header_key NVARCHAR(200) NOT NULL, 
    original_header NVARCHAR(512) NOT NULL, 
    original_value NVARCHAR(max) NOT NULL, 
    date_value DATETIME2 NULL, 
    value_kind VARCHAR(10) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(business_row_id) REFERENCES ds_556 (id), 
    CONSTRAINT uq_ds_556_extension_header UNIQUE (business_row_id, header_key)
);

GO

CREATE TABLE ds_557_extensions (
    id BIGINT NOT NULL IDENTITY, 
    business_row_id BIGINT NOT NULL, 
    header_key NVARCHAR(200) NOT NULL, 
    original_header NVARCHAR(512) NOT NULL, 
    original_value NVARCHAR(max) NOT NULL, 
    date_value DATETIME2 NULL, 
    value_kind VARCHAR(10) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(business_row_id) REFERENCES ds_557 (id), 
    CONSTRAINT uq_ds_557_extension_header UNIQUE (business_row_id, header_key)
);

GO

CREATE TABLE ds_558_extensions (
    id BIGINT NOT NULL IDENTITY, 
    business_row_id BIGINT NOT NULL, 
    header_key NVARCHAR(200) NOT NULL, 
    original_header NVARCHAR(512) NOT NULL, 
    original_value NVARCHAR(max) NOT NULL, 
    date_value DATETIME2 NULL, 
    value_kind VARCHAR(10) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(business_row_id) REFERENCES ds_558 (id), 
    CONSTRAINT uq_ds_558_extension_header UNIQUE (business_row_id, header_key)
);

GO

CREATE TABLE ds_701_extensions (
    id BIGINT NOT NULL IDENTITY, 
    business_row_id BIGINT NOT NULL, 
    header_key NVARCHAR(200) NOT NULL, 
    original_header NVARCHAR(512) NOT NULL, 
    original_value NVARCHAR(max) NOT NULL, 
    date_value DATETIME2 NULL, 
    value_kind VARCHAR(10) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(business_row_id) REFERENCES ds_701 (id), 
    CONSTRAINT uq_ds_701_extension_header UNIQUE (business_row_id, header_key)
);

GO

CREATE TABLE ds_702_extensions (
    id BIGINT NOT NULL IDENTITY, 
    business_row_id BIGINT NOT NULL, 
    header_key NVARCHAR(200) NOT NULL, 
    original_header NVARCHAR(512) NOT NULL, 
    original_value NVARCHAR(max) NOT NULL, 
    date_value DATETIME2 NULL, 
    value_kind VARCHAR(10) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(business_row_id) REFERENCES ds_702 (id), 
    CONSTRAINT uq_ds_702_extension_header UNIQUE (business_row_id, header_key)
);

GO

CREATE TABLE ds_inci_extensions (
    id BIGINT NOT NULL IDENTITY, 
    business_row_id BIGINT NOT NULL, 
    header_key NVARCHAR(200) NOT NULL, 
    original_header NVARCHAR(512) NOT NULL, 
    original_value NVARCHAR(max) NOT NULL, 
    date_value DATETIME2 NULL, 
    value_kind VARCHAR(10) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(business_row_id) REFERENCES ds_inci (id), 
    CONSTRAINT uq_ds_inci_extension_header UNIQUE (business_row_id, header_key)
);

GO

CREATE TABLE ds_resumen_extensions (
    id BIGINT NOT NULL IDENTITY, 
    business_row_id BIGINT NOT NULL, 
    header_key NVARCHAR(200) NOT NULL, 
    original_header NVARCHAR(512) NOT NULL, 
    original_value NVARCHAR(max) NOT NULL, 
    date_value DATETIME2 NULL, 
    value_kind VARCHAR(10) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(business_row_id) REFERENCES ds_resumen (id), 
    CONSTRAINT uq_ds_resumen_extension_header UNIQUE (business_row_id, header_key)
);

GO

CREATE TABLE ds_sel_extensions (
    id BIGINT NOT NULL IDENTITY, 
    business_row_id BIGINT NOT NULL, 
    header_key NVARCHAR(200) NOT NULL, 
    original_header NVARCHAR(512) NOT NULL, 
    original_value NVARCHAR(max) NOT NULL, 
    date_value DATETIME2 NULL, 
    value_kind VARCHAR(10) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(business_row_id) REFERENCES ds_sel (id), 
    CONSTRAINT uq_ds_sel_extension_header UNIQUE (business_row_id, header_key)
);

GO

ALTER TABLE periods ADD CONSTRAINT fk_period_active_run FOREIGN KEY(active_run_id) REFERENCES processing_runs (id);

GO

ALTER TABLE processing_runs ADD CONSTRAINT fk_run_result_document FOREIGN KEY(result_document_id) REFERENCES stored_documents (id);

GO

ALTER TABLE processing_runs ADD CONSTRAINT fk_run_export_document FOREIGN KEY(export_document_id) REFERENCES stored_documents (id);

GO

CREATE VIEW processing_errors AS SELECT * FROM processing_issues WHERE severity = 'error';

GO

CREATE VIEW processing_warnings AS SELECT * FROM processing_issues WHERE severity = 'warning';

GO

INSERT INTO alembic_version (version_num) OUTPUT inserted.version_num VALUES ('20260922_0001');

GO

COMMIT;

GO

