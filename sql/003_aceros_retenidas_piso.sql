-- Piezas retenidas / refundidas en piso (Aceros). Se registran a mano en el tablero por número de orden;
-- el resto de datos (compromiso, ZHAL, acero, entrega y matricero) se lee del consolidado al mostrarlas.
IF OBJECT_ID('cesar.aceros_retenidas_piso') IS NULL
CREATE TABLE cesar.aceros_retenidas_piso (
    id           INT IDENTITY PRIMARY KEY,
    orden        NVARCHAR(40)   NOT NULL,
    fecha        DATE           NOT NULL,   -- día en que se registró como retenida/refundida (cuenta para la línea diaria)
    estatus      NVARCHAR(60)   NULL,
    creado       DATETIME2(0)   NOT NULL,
    actualizado  DATETIME2(0)   NULL,
    usuario      NVARCHAR(80)   NULL,
    ip           VARCHAR(45)    NULL
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_aceros_retenidas_piso_fecha')
CREATE INDEX ix_aceros_retenidas_piso_fecha ON cesar.aceros_retenidas_piso (fecha);
GO
