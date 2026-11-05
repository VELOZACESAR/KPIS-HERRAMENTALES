-- Serigrafía · Logos: la fuente ya no es el Excel "Herramienta Logos Actual.xlsx" sino la app Herramienta Logos.
-- Esa app (herramienta_logos) publica el tablero, el histórico y la gráfica en el esquema HRRM de esta misma base;
-- el tablero guarda una copia en cesar.* para calcular los indicadores:
--   HRRM.VW_HERRAMIENTA_LOGOS -> cesar.seri_logos
--   HRRM.VW_GRAFICA           -> cesar.seri_logos_grafica
--   HRRM.VW_HISTORICO         -> cesar.seri_logos_historico (la última carga de cada orden, ESTADO = CARGADO)
IF OBJECT_ID('cesar.seri_logos_historico') IS NULL
CREATE TABLE cesar.seri_logos_historico (
    fila         INT           NOT NULL PRIMARY KEY,
    id_cargue    INT           NOT NULL,
    fecha        DATE          NULL,
    orden        NVARCHAR(40)  NULL,
    responsable  NVARCHAR(80)  NULL
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_seri_logos_historico_fecha')
CREATE INDEX IX_seri_logos_historico_fecha ON cesar.seri_logos_historico (fecha);
GO
