-- Indicadores diarios (oct-2026): la hoja Vitrojet trae capacidad y retenidas por tipo de vitro.
-- "capacidad" queda como la de vitros estándar; "piezas_quietas" como la suma de las tres retenidas.
IF COL_LENGTH('cesar.seri_ind_vitrojet', 'cap_logo') IS NULL ALTER TABLE cesar.seri_ind_vitrojet ADD cap_logo FLOAT NULL;
GO
IF COL_LENGTH('cesar.seri_ind_vitrojet', 'cap_pp') IS NULL ALTER TABLE cesar.seri_ind_vitrojet ADD cap_pp FLOAT NULL;
GO
IF COL_LENGTH('cesar.seri_ind_vitrojet', 'ret_logo') IS NULL ALTER TABLE cesar.seri_ind_vitrojet ADD ret_logo FLOAT NULL;
GO
IF COL_LENGTH('cesar.seri_ind_vitrojet', 'ret_estandar') IS NULL ALTER TABLE cesar.seri_ind_vitrojet ADD ret_estandar FLOAT NULL;
GO
IF COL_LENGTH('cesar.seri_ind_vitrojet', 'ret_pp') IS NULL ALTER TABLE cesar.seri_ind_vitrojet ADD ret_pp FLOAT NULL;
GO
