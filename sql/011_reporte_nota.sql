-- Notas editables de los reportes del Resumen (ej. Estatus de FULL KIT): los renglones de cada sección, como lista JSON.
-- Los escribe cualquiera desde el tablero (con la clave de edición); todos ven lo mismo.
IF OBJECT_ID('cesar.reporte_nota') IS NULL
CREATE TABLE cesar.reporte_nota (
    reporte      VARCHAR(40)    NOT NULL,
    seccion      VARCHAR(40)    NOT NULL,
    lineas       NVARCHAR(MAX)  NOT NULL,   -- ["renglón 1", "renglón 2", ...]
    actualizado  DATETIME2(0)   NOT NULL,
    usuario      NVARCHAR(80)   NULL,
    CONSTRAINT PK_reporte_nota PRIMARY KEY (reporte, seccion)
);
GO
