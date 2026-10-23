-- Historial de envíos del resumen a Teams (botón "Enviar a Teams").
IF OBJECT_ID('cesar.reporte_envio') IS NULL
CREATE TABLE cesar.reporte_envio (
    id       INT IDENTITY PRIMARY KEY,
    fecha    DATETIME2(0)    NOT NULL,
    estado   VARCHAR(10)     NOT NULL,
    bytes    INT             NULL,
    detalle  NVARCHAR(1000)  NULL,
    usuario  NVARCHAR(80)    NULL,
    ip       VARCHAR(45)     NULL,
    pc       NVARCHAR(60)    NULL
);
GO
