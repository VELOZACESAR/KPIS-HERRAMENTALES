-- Lo que se pide a mantenimiento: los moldes que el sistema de puntaje marca POR MANTENIMIENTO
-- (INV.MANTENIMIENTO_MOLDES_GRUPO). Esa tabla solo guarda el estado actual, así que el tablero
-- la fotografía cada pocos minutos: una fila por día y repetición que estuvo en alerta, con la
-- primera y la última vez que se vio ese día. Con eso se sabe qué alertas son nuevas cada día y
-- cuántos mantenimientos finalizados atendieron una alerta.
IF OBJECT_ID('cesar.mant_alerta') IS NULL
CREATE TABLE cesar.mant_alerta (
    fecha       DATE           NOT NULL,
    cod_her     NVARCHAR(20)   NOT NULL,
    version     NVARCHAR(10)   NOT NULL,
    pieza       NVARCHAR(10)   NOT NULL,
    repeticion  NVARCHAR(20)   NOT NULL,
    puntaje     FLOAT          NULL,
    desde       DATETIME2(0)   NOT NULL,
    hasta       DATETIME2(0)   NOT NULL,
    CONSTRAINT PK_mant_alerta PRIMARY KEY (fecha, cod_her, version, pieza, repeticion)
);
GO

-- Vehículo y categoría de cada molde, con la misma regla de cesar.vw_mantenimiento (el vehículo más
-- frecuente en el inventario), para repartir las alertas por categoría igual que los finalizados.
CREATE OR ALTER VIEW cesar.vw_molde_categoria AS
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
    v.Tipo                              AS tipo,
    v.CodMolde                          AS cod_molde,
    v.Vehiculo                          AS vehiculo,
    COALESCE(c.categoria, N'Retrofit')  AS categoria
FROM vehiculo_molde v
OUTER APPLY (
    SELECT TOP 1 cv.categoria
    FROM cesar.categoria_vehiculo cv
    WHERE v.Vehiculo LIKE cv.patron
    ORDER BY cv.orden
) c;
GO
