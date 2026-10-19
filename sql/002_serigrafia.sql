-- Serigrafía: logos, vitros normales (Vitrojet), pasta de plata e indicadores diarios (piezas retenidas / screens).

IF OBJECT_ID('cesar.seri_logos') IS NULL
CREATE TABLE cesar.seri_logos (
    fila             INT            NOT NULL PRIMARY KEY,
    id_cargue        INT            NOT NULL,
    pedido_genesis   NVARCHAR(40)   NULL,
    orden            NVARCHAR(40)   NULL,
    trazabilidad     NVARCHAR(80)   NULL,
    logo             NVARCHAR(60)   NULL,
    tipo_logo        NVARCHAR(60)   NULL,
    inv_status       NVARCHAR(40)   NULL,
    zfer             NVARCHAR(40)   NULL,
    vehiculo         NVARCHAR(200)  NULL,
    cliente          NVARCHAR(200)  NULL,
    puesto_trabajo   NVARCHAR(40)   NULL,
    fecha_lib_toc    DATE           NULL,
    nombre_archivo   NVARCHAR(400)  NULL,
    prioridad        NVARCHAR(40)   NULL,
    estado           NVARCHAR(40)   NULL,
    responsable      NVARCHAR(80)   NULL,
    plan_corte       NVARCHAR(80)   NULL,
    fullkit          NVARCHAR(60)   NULL
);
GO

IF OBJECT_ID('cesar.seri_vitro_cal') IS NULL
CREATE TABLE cesar.seri_vitro_cal (
    fila             INT            NOT NULL PRIMARY KEY,
    id_cargue        INT            NOT NULL,
    pedido_genesis   NVARCHAR(40)   NULL,
    orden            NVARCHAR(40)   NULL,
    zfer             NVARCHAR(40)   NULL,
    puesto_trabajo   NVARCHAR(40)   NULL,
    fecha_lib_toc    DATE           NULL,
    vehiculo         NVARCHAR(200)  NULL,
    descripcion      NVARCHAR(60)   NULL,
    componente       NVARCHAR(40)   NULL,
    denominacion     NVARCHAR(120)  NULL,
    codigo_vitro     NVARCHAR(60)   NULL,
    status_vitrojet  NVARCHAR(40)   NULL
);
GO

IF OBJECT_ID('cesar.seri_vitro_hechos') IS NULL
CREATE TABLE cesar.seri_vitro_hechos (
    fila         INT            NOT NULL PRIMARY KEY,
    id_cargue    INT            NOT NULL,
    fecha        DATE           NULL,
    vitro        NVARCHAR(60)   NULL,
    vehiculo     NVARCHAR(200)  NULL,
    codigo       NVARCHAR(60)   NULL,
    tipo         NVARCHAR(30)   NULL,
    estatus      NVARCHAR(30)   NULL,
    responsable  NVARCHAR(60)   NULL
);
GO

IF OBJECT_ID('cesar.seri_pp_consulta') IS NULL
CREATE TABLE cesar.seri_pp_consulta (
    fila            INT            NOT NULL PRIMARY KEY,
    id_cargue       INT            NOT NULL,
    pedido_genesis  NVARCHAR(40)   NULL,
    orden           NVARCHAR(40)   NULL,
    zfer            NVARCHAR(40)   NULL,
    vehiculo        NVARCHAR(200)  NULL,
    cliente         NVARCHAR(200)  NULL,
    puesto_trabajo  NVARCHAR(40)   NULL,
    componente      NVARCHAR(40)   NULL,
    descripcion     NVARCHAR(60)   NULL,
    denominacion    NVARCHAR(120)  NULL,
    inventario_1    NVARCHAR(40)   NULL,
    inventario_2    NVARCHAR(40)   NULL,
    inventario_3    NVARCHAR(40)   NULL
);
GO

IF OBJECT_ID('cesar.seri_pp_archivos') IS NULL
CREATE TABLE cesar.seri_pp_archivos (
    fila          INT            NOT NULL PRIMARY KEY,
    id_cargue     INT            NOT NULL,
    fecha         DATE           NULL,
    zfer          NVARCHAR(40)   NULL,
    vehiculo      NVARCHAR(200)  NULL,
    herramental   NVARCHAR(120)  NULL,
    estatus_vitro NVARCHAR(40)   NULL,
    responsable   NVARCHAR(60)   NULL,
    archivo_s     NVARCHAR(60)   NULL,
    caso          NVARCHAR(40)   NULL
);
GO

IF OBJECT_ID('cesar.seri_ind_vitrojet') IS NULL
CREATE TABLE cesar.seri_ind_vitrojet (
    fila            INT    NOT NULL PRIMARY KEY,
    id_cargue       INT    NOT NULL,
    fecha           DATE   NULL,
    vitros_nuevos   FLOAT  NULL,
    piezas_quietas  FLOAT  NULL,
    capacidad       FLOAT  NULL
);
GO

IF OBJECT_ID('cesar.seri_ind_mallas') IS NULL
CREATE TABLE cesar.seri_ind_mallas (
    fila             INT    NOT NULL PRIMARY KEY,
    id_cargue        INT    NOT NULL,
    fecha            DATE   NULL,
    mallas           FLOAT  NULL,
    logos            FLOAT  NULL,
    trazabilidades   FLOAT  NULL,
    piezas_quietas   FLOAT  NULL
);
GO
