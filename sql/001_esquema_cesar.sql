-- Esquema propio del tablero de Herramentales dentro de AGP_Ingenieria.
-- Se puede correr las veces que sea: solo crea lo que falta.

IF SCHEMA_ID('cesar') IS NULL EXEC('CREATE SCHEMA cesar');
GO

IF OBJECT_ID('cesar.cargue') IS NULL
CREATE TABLE cesar.cargue (
    id              INT IDENTITY PRIMARY KEY,
    fuente          VARCHAR(40)    NOT NULL,
    archivo         NVARCHAR(400)  NULL,
    sha256          CHAR(64)       NULL,
    modificado      DATETIME2(0)   NULL,
    inicio          DATETIME2(0)   NOT NULL,
    fin             DATETIME2(0)   NULL,
    filas           INT            NULL,
    estado          VARCHAR(12)    NOT NULL,
    mensaje         NVARCHAR(MAX)  NULL
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_cargue_fuente')
CREATE INDEX IX_cargue_fuente ON cesar.cargue (fuente, id DESC) INCLUDE (estado, sha256, modificado, fin, filas);
GO

IF OBJECT_ID('cesar.aceros_consolidado') IS NULL
CREATE TABLE cesar.aceros_consolidado (
    fila                INT            NOT NULL PRIMARY KEY,
    id_cargue           INT            NOT NULL,
    pedido_genesis      NVARCHAR(40)   NULL,
    pedido_sap          NVARCHAR(40)   NULL,
    orden               NVARCHAR(40)   NULL,
    zfer                NVARCHAR(40)   NULL,
    zhal                NVARCHAR(40)   NULL,
    acero               NVARCHAR(80)   NULL,
    vehiculo            NVARCHAR(200)  NULL,
    fecha_envio_planta  DATETIME2(0)   NULL,
    tipo_pedido         NVARCHAR(60)   NULL,
    pieza               NVARCHAR(40)   NULL,
    corte               NVARCHAR(80)   NULL,
    material            NVARCHAR(60)   NULL,
    entrega_produccion  DATE           NULL,
    puesto_trabajo      NVARCHAR(40)   NULL,
    prioridad           NVARCHAR(40)   NULL,
    plano               NVARCHAR(40)   NULL,
    puntos              FLOAT          NULL,
    fecha_fabricacion   DATE           NULL,
    operario            NVARCHAR(120)  NULL,
    estado              NVARCHAR(60)   NULL,
    mercado             NVARCHAR(60)   NULL
);
GO

IF OBJECT_ID('cesar.aceros_rechazos') IS NULL
CREATE TABLE cesar.aceros_rechazos (
    fila        INT            NOT NULL PRIMARY KEY,
    id_cargue   INT            NOT NULL,
    orden       NVARCHAR(40)   NULL,
    zfer        NVARCHAR(40)   NULL,
    zhal        NVARCHAR(40)   NULL,
    acero       NVARCHAR(80)   NULL,
    vehiculo    NVARCHAR(200)  NULL,
    plano       NVARCHAR(40)   NULL,
    fecha       DATE           NULL
);
GO

IF OBJECT_ID('cesar.pedidos_corte') IS NULL
CREATE TABLE cesar.pedidos_corte (
    fila            INT             NOT NULL PRIMARY KEY,
    id_cargue       INT             NOT NULL,
    servicio        NVARCHAR(40)    NULL,
    fecha           DATE            NULL,
    material        NVARCHAR(80)    NULL,
    comentario      NVARCHAR(400)   NULL,
    marcos          FLOAT           NULL,
    orden_trabajo   NVARCHAR(400)   NULL,
    valor           DECIMAL(18,2)   NULL
);
GO

IF OBJECT_ID('cesar.x5_inventario') IS NULL
CREATE TABLE cesar.x5_inventario (
    fila        INT            NOT NULL PRIMARY KEY,
    id_cargue   INT            NOT NULL,
    pieza       NVARCHAR(120)  NOT NULL,
    matriceria  FLOAT          NULL,
    calidad     FLOAT          NULL
);
GO

IF OBJECT_ID('cesar.fila_moldes') IS NULL
CREATE TABLE cesar.fila_moldes (
    fila             INT            NOT NULL PRIMARY KEY,
    id_cargue        INT            NOT NULL,
    fecha_solicitud  DATE           NULL,
    herramental      NVARCHAR(40)   NULL,
    codigo           NVARCHAR(60)   NULL,
    zhal             NVARCHAR(60)   NULL,
    pieza            NVARCHAR(40)   NULL,
    repeticion       NVARCHAR(20)   NULL,
    completo         NVARCHAR(80)   NULL,
    vehiculo         NVARCHAR(200)  NULL,
    fecha_entrega    DATE           NULL,
    fabricante       NVARCHAR(120)  NULL,
    estatus          NVARCHAR(40)   NULL,
    patron           NVARCHAR(60)   NULL,
    comentario       NVARCHAR(400)  NULL,
    tamano           NVARCHAR(20)   NULL,
    tiempo_h         FLOAT          NULL
);
GO

-- Lo que los Excel no guardan (fila de aceros, piezas retenidas, inventario X5, cola de moldes):
-- una foto por día, la última corrida del día manda.
IF OBJECT_ID('cesar.foto_diaria') IS NULL
CREATE TABLE cesar.foto_diaria (
    fecha        DATE          NOT NULL,
    indicador    VARCHAR(60)   NOT NULL,
    valor        FLOAT         NULL,
    actualizado  DATETIME2(0)  NOT NULL,
    CONSTRAINT PK_foto_diaria PRIMARY KEY (fecha, indicador)
);
GO

IF OBJECT_ID('cesar.x5_inventario_diario') IS NULL
CREATE TABLE cesar.x5_inventario_diario (
    fecha        DATE           NOT NULL,
    pieza        NVARCHAR(120)  NOT NULL,
    matriceria   FLOAT          NULL,
    calidad      FLOAT          NULL,
    actualizado  DATETIME2(0)   NOT NULL,
    CONSTRAINT PK_x5_inventario_diario PRIMARY KEY (fecha, pieza)
);
GO

IF OBJECT_ID('cesar.valor_manual') IS NULL
CREATE TABLE cesar.valor_manual (
    clave        VARCHAR(80)    NOT NULL PRIMARY KEY,
    valor        FLOAT          NULL,
    actualizado  DATETIME2(0)   NOT NULL,
    usuario      NVARCHAR(80)   NULL
);
GO

IF OBJECT_ID('cesar.valor_manual_hist') IS NULL
CREATE TABLE cesar.valor_manual_hist (
    id           INT IDENTITY PRIMARY KEY,
    clave        VARCHAR(80)    NOT NULL,
    valor_antes  FLOAT          NULL,
    valor        FLOAT          NULL,
    actualizado  DATETIME2(0)   NOT NULL,
    usuario      NVARCHAR(80)   NULL,
    ip           VARCHAR(45)    NULL
);
GO

IF OBJECT_ID('cesar.parametro') IS NULL
CREATE TABLE cesar.parametro (
    clave        VARCHAR(60)    NOT NULL PRIMARY KEY,
    valor        NVARCHAR(200)  NOT NULL,
    descripcion  NVARCHAR(400)  NULL
);
GO

IF OBJECT_ID('cesar.festivo') IS NULL
CREATE TABLE cesar.festivo (
    fecha   DATE          NOT NULL PRIMARY KEY,
    nombre  NVARCHAR(80)  NOT NULL
);
GO

IF OBJECT_ID('cesar.material') IS NULL
CREATE TABLE cesar.material (
    texto     NVARCHAR(60)  NOT NULL PRIMARY KEY,
    material  NVARCHAR(40)  NOT NULL
);
GO

IF OBJECT_ID('cesar.material_orden') IS NULL
CREATE TABLE cesar.material_orden (
    material  NVARCHAR(40)  NOT NULL PRIMARY KEY,
    orden     INT           NOT NULL,
    color     VARCHAR(9)    NULL
);
GO

IF OBJECT_ID('cesar.equivalencia') IS NULL
CREATE TABLE cesar.equivalencia (
    material  NVARCHAR(40)  NOT NULL,
    pieza     INT           NOT NULL,
    factor    FLOAT         NOT NULL,
    CONSTRAINT PK_equivalencia PRIMARY KEY (material, pieza)
);
GO

IF OBJECT_ID('cesar.operario_regla') IS NULL
CREATE TABLE cesar.operario_regla (
    nombre  NVARCHAR(120)  NOT NULL PRIMARY KEY,
    accion  VARCHAR(10)    NOT NULL CHECK (accion IN ('excluir', 'alias', 'vacio')),
    alias   NVARCHAR(120)  NULL
);
GO

IF OBJECT_ID('cesar.categoria_vehiculo') IS NULL
CREATE TABLE cesar.categoria_vehiculo (
    id         INT IDENTITY PRIMARY KEY,
    categoria  NVARCHAR(60)   NOT NULL,
    patron     NVARCHAR(120)  NOT NULL,
    orden      INT            NOT NULL
);
GO

-- Mantenimientos de moldes y galgas (app Control Inventarios) con su vehículo y la categoría del tablero.
-- Solo lectura sobre dbo: el tablero nunca escribe en las tablas de la app.
CREATE OR ALTER VIEW cesar.vw_mantenimiento AS
WITH vehiculo_molde AS (
    SELECT Tipo, CodMolde, Vehiculo
    FROM (
        SELECT Tipo, CodMolde, LTRIM(RTRIM(Vehiculo)) AS Vehiculo,
               ROW_NUMBER() OVER (PARTITION BY Tipo, CodMolde ORDER BY COUNT(*) DESC, MAX(IdRegistro) DESC) AS rn
        FROM dbo.AppControlInventarios_RegistroInventario
        WHERE NULLIF(NULLIF(LTRIM(RTRIM(Vehiculo)), ''), '0') IS NOT NULL
        GROUP BY Tipo, CodMolde, LTRIM(RTRIM(Vehiculo))
    ) v
    WHERE rn = 1
)
SELECT
    h.IdManten                                                         AS id,
    h.Tipo                                                             AS tipo,
    h.CodHer                                                           AS cod_her,
    h.Version                                                          AS version,
    h.Pieza                                                            AS pieza,
    h.Repeticion                                                       AS repeticion,
    LTRIM(RTRIM(h.Estatus))                                            AS estatus,
    NULLIF(LTRIM(RTRIM(h.TipoMant)), '')                               AS tipo_mant,
    h.EstadoPostes                                                     AS estado_postes,
    h.PatronReferencia                                                 AS patron,
    LTRIM(RTRIM(REPLACE(COALESCE(NULLIF(LTRIM(RTRIM(h.Entrega)), ''), h.CreadoPor), '.', ''))) AS persona,
    NULLIF(LTRIM(RTRIM(h.Recibe)), '')                                 AS recibe,
    h.FechaCreateMant                                                  AS inicio,
    h.FechaReleaseMant                                                 AS fin,
    CASE WHEN h.FechaReleaseMant >= h.FechaCreateMant
         THEN DATEDIFF(MINUTE, h.FechaCreateMant, h.FechaReleaseMant) END AS minutos,
    v.Vehiculo                                                         AS vehiculo,
    COALESCE(c.categoria, N'Retrofit')                                 AS categoria
FROM dbo.AppControlInventarios_ManttoHead h
LEFT JOIN vehiculo_molde v ON v.Tipo = h.Tipo AND v.CodMolde = h.CodHer
OUTER APPLY (
    SELECT TOP 1 cv.categoria
    FROM cesar.categoria_vehiculo cv
    WHERE v.Vehiculo LIKE cv.patron
    ORDER BY cv.orden
) c;
GO
