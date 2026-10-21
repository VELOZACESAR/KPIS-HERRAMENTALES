-- Herramienta Logos Actual.xlsx, hoja "Historico": logos hechos por día y responsable (FechaCreacion, ESTADO = OK).
-- Alimenta lo hecho en la gráfica de Vitros logos (relleno de la barra de carga, apilado por responsable).
IF OBJECT_ID('cesar.seri_logos_hechos') IS NULL
CREATE TABLE cesar.seri_logos_hechos (
    fila         INT           NOT NULL,
    id_cargue    INT           NOT NULL,
    fecha        DATE          NOT NULL,
    responsable  NVARCHAR(80)  NULL,
    n            INT           NOT NULL
);
GO
