-- Conserva la situación calculada por Herramienta Logos para separar carga lista de órdenes ya cargadas o sin vitro SAP.
IF COL_LENGTH('cesar.seri_logos', 'situacion') IS NULL
    ALTER TABLE cesar.seri_logos ADD situacion NVARCHAR(40) NULL;
GO
