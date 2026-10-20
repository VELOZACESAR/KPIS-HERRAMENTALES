-- Indicadores diarios.xlsx: columna "Vitros PP" = carga del día de pasta de plata (la escribe el equipo en el Excel).
-- Se agrega en las dos hojas leídas (VITROJET y MALLAS) porque la columna puede quedar en cualquiera de ellas.
IF COL_LENGTH('cesar.seri_ind_vitrojet', 'vitros_pp') IS NULL
    ALTER TABLE cesar.seri_ind_vitrojet ADD vitros_pp FLOAT NULL;
GO

IF COL_LENGTH('cesar.seri_ind_mallas', 'vitros_pp') IS NULL
    ALTER TABLE cesar.seri_ind_mallas ADD vitros_pp FLOAT NULL;
GO
