-- Necesidad de mantenimiento según SmartBending: repeticiones POR MANTENIMIENTO cuyo molde está en el plan de hornos
-- (origen 'Plan') o tiene piezas esperándolo en un puesto (origen = el puesto más cercano al horno). El plan cambia
-- durante el día, así que el servidor lo fotografía cada pocos minutos y suma lo nuevo: una fila por día y repetición
-- que fue necesidad en algún momento de ese día, con la primera y la última vez que se vio.
IF OBJECT_ID('cesar.mant_necesidad') IS NULL
CREATE TABLE cesar.mant_necesidad (
    fecha       DATE           NOT NULL,
    cod_her     NVARCHAR(20)   NOT NULL,
    version     NVARCHAR(10)   NOT NULL,
    pieza       NVARCHAR(10)   NOT NULL,
    repeticion  NVARCHAR(20)   NOT NULL,
    categoria   NVARCHAR(40)   NOT NULL,
    origen      NVARCHAR(20)   NOT NULL,
    desde       DATETIME2(0)   NOT NULL,
    hasta       DATETIME2(0)   NOT NULL,
    CONSTRAINT PK_mant_necesidad PRIMARY KEY (fecha, cod_her, version, pieza, repeticion)
);
GO
