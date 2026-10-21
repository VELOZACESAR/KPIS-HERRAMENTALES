-- Indicadores diarios.xlsx: capacidad diaria de vitros pasta de plata (encabezado con "CAPACIDAD" y "PP" o "PLATA").
-- Se agrega en las dos hojas leídas (VITROJET y MALLAS) porque la columna puede quedar en cualquiera de ellas.
IF COL_LENGTH('cesar.seri_ind_vitrojet', 'capacidad_pp') IS NULL
    ALTER TABLE cesar.seri_ind_vitrojet ADD capacidad_pp FLOAT NULL;
GO

IF COL_LENGTH('cesar.seri_ind_mallas', 'capacidad_pp') IS NULL
    ALTER TABLE cesar.seri_ind_mallas ADD capacidad_pp FLOAT NULL;
GO
