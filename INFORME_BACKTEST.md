# Backtest cripto ampliado — resultados al 05-11-2026

> **Iteración posterior a la auditoría:** ver [ITERACION_RESULTADO.md](ITERACION_RESULTADO.md). Se probaron variantes nuevas con el motor de unidades/efectivo y se congeló una candidata experimental de tendencia confirmada + sizing por volatilidad en BTC/ETH. Los resultados siguen siendo retrospectivos; no sustituyen una validación con datos nuevos.

> **Revisión del 06-11-2026:** las conclusiones históricas siguientes son provisionales. La auditoría encontró errores de mantenimiento de posiciones, costos y selección temporal. El 13% de la mezcla 60/40 no debe usarse como evidencia validada. Consultar **[REVISION_AUDITORIA.md](REVISION_AUDITORIA.md)** y los nuevos `audit_results.csv`/`audit_backtests.py` para el recálculo independiente de candidatas spot. Se conserva este informe como registro de intentos, no como recomendación operativa.

## Qué salió mejor

No apareció una estrategia que gane de forma estadísticamente convincente a comprar y mantener. La mejor candidata nueva para **BTC spot con menos caídas** fue una votación de tendencias multi-horizonte:

1. Al cierre diario, calcular el retorno de BTC en los últimos 30, 90 y 180 días.
2. Mantener BTC si al menos 2 de esos 3 retornos son positivos; en caso contrario, efectivo.
3. Ejecutar con demora conservadora de una vela diaria desde la señal; sin apalancamiento. Costos de 10 pb por notional operado y estrés a 20 pb.

| BTC, 2023-01-01 a 2026-11-05 | CAGR neta | Sharpe | Vol. anual | Caída máx. |
|---|---:|---:|---:|---:|
| Comprar y mantener | 48,7% | 1,09 | 46,2% | -53,0% |
| Voto 30/90/180, costo 10 pb | 38,2% | 1,07 | 36,2% | -30,4% |
| Voto 30/90/180, costo 20 pb | 36,2% | 1,03 | 35,5% | -31,3% |

La señal baja bastante el riesgo realizado, pero no mejora el Sharpe sobre BTC pasivo ni su retorno compuesto en todo el tramo. El resultado no prueba alpha. En 2024–2026 dio un resultado mejor que BTC pasivo; ese intervalo favorable no alcanza para concluir que continuará.

## Estrategias comparadas

Probé 14 reglas además del benchmark: SMA 200; cruces SMA 50/200 y EMA 50/200; momentum de 90 días y 12–1 meses; voto de tendencias 30/90/180; MACD 12/26/9; breakout Donchian 55/20; RSI(2) y RSI(14) de reversión; Bollinger 20/2; objetivo de volatilidad del 20%; y SMA 200 combinada con objetivos de volatilidad del 20% y 30%.

La tabla muestra las reglas más competitivas en BTC en el tramo posterior al período inicial de 2017–2022, con 10 pb por notional y demora conservadora. El benchmark pasivo tuvo el mayor Sharpe de esta prueba; el voto multi-horizonte estuvo cerca y redujo el drawdown. EMA 50/200 también redujo la caída, pero fue menos consistente por regímenes. RSI y Bollinger no fueron buenos candidatos; MACD y Donchian lideraron la etapa de entrenamiento y luego se debilitaron.

| Regla | CAGR | Sharpe | Caída máx. |
|---|---:|---:|---:|
| Comprar y mantener | 48,7% | 1,09 | -53,0% |
| Voto multi-horizonte | 38,2% | 1,07 | -30,4% |
| EMA 50/200 | 39,2% | 1,03 | -28,1% |
| Volatilidad objetivo 20% | 21,0% | 0,95 | -36,0% |
| Donchian 55/20 | 22,9% | 0,86 | -32,4% |

## ¿Fue suerte u overfitting?

Hice tres comprobaciones adicionales:

- **Regímenes:** la regla multi-horizonte mostró CAGR/Sharpe de 39,3%/0,90 en el tramo inicial 2017–2022; 13,7%/0,51 en 2021–2023; y 42,4%/1,18 en 2024–2026. El comportamiento cambia bastante entre períodos.
- **Sensibilidad:** moví los horizontes a combinaciones cercanas (20/60/120, 40/120/240 y 60/120/252) y exigí 1, 2 o 3 señales positivas. No hay un único pico perfecto, pero el Sharpe posterior varió de 0,72 a 1,13 según la variante; la configuración original no es claramente superior.
- **Selección walk-forward:** cada enero escogí entre las 15 reglas la de mayor Sharpe de los 3 años previos y la operé el año siguiente, desde 2021. Resultado: CAGR 19,9%, Sharpe 0,65 y caída máx. -51,1%; BTC pasivo en las mismas fechas: 18,0%, 0,57 y -76,6%. Pero un bootstrap por bloques de 30 días dio una diferencia media aritmética anualizada de -6,2 puntos porcentuales, intervalo 95% de -33,6 a +22,7 y solo 32% de réplicas con diferencia positiva. Es una mejora histórica de riesgo, no evidencia estadística de mayor retorno esperado.

La votación de tendencias fue floja en ETH y BNB durante la validación (CAGR 8,1% y 1,1%), aunque mejor en BTC y SOL. No asumiría que se transfiere a todas las monedas.

## Carry spot–perpetuo: prueba adicional

Probé una posición delta-neutral: comprar spot y vender igual nominal de perpetuo cuando el promedio de los últimos 7 pagos de funding es positivo; si no, efectivo. La decisión usa el funding ya publicado y mantiene la posición hasta el siguiente evento. Se alinearon los datos al segundo, porque Binance puede marcar el pago con unos milisegundos de diferencia respecto del cierre de vela.

En BTC, desde 2023 al último funding completo del 05-11 local, rindió **1,99% anual neto** sobre el capital bruto de ambas patas (spot + perpetuo), Sharpe 2,32 en el recálculo con velas de 4h y caída máxima 2,48%, suponiendo fee taker de 10 pb en spot y 5 pb en futuros, cero deslizamiento y cero rendimiento sobre el efectivo. El cálculo anterior reportaba Sharpe 4,14 con otra frecuencia de medición; para compararlo con las pruebas nuevas, usar 2,32. Con el doble de fees (20 + 10 pb), la prueba anterior bajó a **0,30% anual**, Sharpe 0,38 y drawdown 5,79%. ETH quedó en 1,83% anual con fees base y -0,10% con el estrés; BNB y SOL perdieron incluso con fees base. La versión que reacciona a cada pago fue claramente perdedora por rotación.

No la consideraría ganadora: el carry depende casi enteramente del funding, la ganancia es pequeña frente al capital requerido, y el test no incluye deslizamiento, costo de capital, margen/colateral ni ampliaciones bruscas de basis. Su Sharpe alto refleja variación baja en esta muestra, no una rentabilidad alta garantizada. Binance documenta el histórico de funding y sus intervalos, que pueden cambiar ([API de funding](https://developers.binance.info/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data)); el carry spot-futuros aparece en investigación del BIS, con fricciones reales entre mercados ([BIS, Crypto carry](https://www.bis.org/publ/work1087.pdf)).

## Datos y límites

Velas diarias OHLCV de Binance Spot hasta 2026-11-05 local; BTC y ETH desde 2017-08-17, BNB desde 2017-11-06 y SOL desde 2020-08-11. En las reglas de precio faltan spread, deslizamiento, impuestos y rendimiento del efectivo; fees fijos aproximados aplicados a todo el historial. En carry se incluye funding histórico, pero no spread/slippage, costo de capital ni riesgo de liquidación/margen. La cartera de cuatro monedas usa activos actuales, con sesgo de supervivencia; es diagnóstica. Los datos se inspeccionaron durante la búsqueda: la validación posterior a 2022 no es ciega.

La investigación respalda probar tendencia con distintos horizontes, pero también documenta sensibilidad a costos y riesgo de colas extremas ([Le y Ruthbah, 2023](https://www.monash.edu/__data/assets/pdf_file/0011/3744821/Trend-following-Strategies-for-Crypto-Investors.pdf); [Grobys et al., 2025](https://link.springer.com/article/10.1007/s11408-025-00474-9)). La comisión de referencia Binance regular es 0,10% Spot y 0,05% taker USDⓈ-M, sujeta a cuenta ([Spot](https://www.binance.com/en/fee/trading), [futuros](https://www.binance.com/en-NG/support/faq/detail/360033544231)); velas desde la [API Spot](https://developers.binance.com/en/docs/products/spot/rest-api).

## Ampliación: futuros, shorts, funding y 12h (05-11-2026)

Sumé más de 20 reglas/variantes: cruces EMA, Donchian, momentum, reversión de 1 vela, RSI(2), Bollinger, reversión por volumen, shorts tras desplomes, compra del desplome, expansión de volatilidad, squeeze breakout, VWAP, filtro de tendencia tras caída, filtro de iliquidez Amihud, fades por funding, tendencia con objetivo de volatilidad, carry spot–perpetuo, momentum semanal long/short entre BTC/ETH/BNB/SOL y reversión de sesión de 12h. Para futuros usé velas 4h desde 2020 (1h desde 2022), fees taker de 5 pb por notional operado, funding histórico y señal aplicada una vela después. Simulé equity y liquidación intrabar con margen de mantenimiento supuesto de 0,5% y cargo de liquidación 0,2%; no reproduce las bandas de margen exactas del exchange y no incluye spread/deslizamiento.

### Dos ideas con potencial para vigilar

**1. BTC tendencia larga/efectivo (1x).** Mantener largo si EMA20 > EMA100 y cierre > SMA200 (en velas de 4h; SMA200 equivale a unas 33 jornadas), si no, efectivo. En 2023–05 nov 2026: CAGR neta 35,8%, Sharpe 1,15 y drawdown -30,5%; BTC pasivo en el mismo test: 38,6%, 0,89 y -62,1%. Es una regla de control de riesgo que históricamente sacrificó algo de retorno y redujo mucho las caídas; no venció a BTC en CAGR. Con 2x el CAGR simulado subió a 62,4%, pero el drawdown creció a -47,6%; no recomiendo ese apalancamiento. La estrategia no fue seleccionada por su resultado de test: quedó entre las tres mejores reglas por Sharpe en el tramo de entrenamiento 2020–2022.

**2. ETH comprar capitulación (solo observación/paper).** Si ETH cae más de 8% en las últimas 24h y el volumen supera 1,5 desviaciones estándar de su media de 30 velas, comprar en la apertura siguiente y mantener 8h. En 2023–05 nov 2026, 1x: CAGR 13,8%, Sharpe 1,21, drawdown -10,3%; ETH pasivo: 5,2%, 0,46, -80,8%. Con 10 pb de fee por notional, dio 12,9% CAGR y Sharpe 1,14. Pero en 2020–2022 perdió 12,5% anualizado (Sharpe -0,36), y la ganancia de validación vino sobre todo de 2024–2025; en 2026 YTD rindió 1,6% (Sharpe 0,22). Variantes cercanas (6–10% de caída, umbral de volumen 1–2 y 4–12h de tenencia) cambiaron bastante el resultado. Esta señal es prometedora pero muy expuesta a selección de parámetros/regímenes: paper trading solamente.

No presentaría shorts o alto apalancamiento como ganadores. Buy-and-hold short en BTC/ETH fue liquidado en la prueba; 3x/5x generó caídas cercanas a perder todo el capital en varios cruces de tendencia. La reversión short de 12h perdió en BTC y ETH en ambos tramos y con 1x; a 2x/3x empeoró, y en ETH 3x liquidó. Los shorts direccionales no superaron consistentemente comprar/esperar. Una conversación de Reddit también relata que agregar shorts empeoró 10 estrategias y menciona filtros de momentum/funding como ideas, no como evidencia comprobada ([prueba de shorts](https://www.reddit.com/r/algotradingcrypto/comments/1visv9c/spent_the_weekend_adding_a_short_side_to_10/); [idea del filtro BTC 3 días](https://www.reddit.com/r/algotrading/comments/1naoem2/list_of_the_most_basic_algorithmic/)). Un estudio reciente de momentum/reversión intradía encuentra diferencias por sesión, pero advierte sobre costos y selección de sesiones, así que lo usé como hipótesis y la reversión 12h simple falló en nuestros datos ([estudio](https://www.mdpi.com/1911-8074/19/9/692)).

### Qué me llevaría

La mejor candidata práctica es BTC tendencia larga/efectivo por su regla simple y caídas menores, no por mayor rentabilidad. La compra de capitulación en ETH es una apuesta experimental de baja frecuencia: está bien en el test reciente, mal en entrenamiento y sensible a parámetros. Probé más de 20 ideas y no apareció una estrategia que pueda declararse robustamente rentable o lista para operar con dinero real. Los períodos de validación se inspeccionaron durante la búsqueda, así que ya no son una muestra ciega. Recomendación: paper trading con fees/spread observados y registrar cada señal/fill durante varios meses, sin subir de 1x.




**Archivos reproducibles:** `expanded_backtest.py`, `multihorizon_sensitivity.py`, `walkforward_backtest.py`, `carry_universe.py`, `crazy_strategy_backtest.py`, `crash_fade_sensitivity.py`, `session_reversal_backtest.py`; resúmenes CSV junto al informe (`crazy_4h_summary.csv`, `crash_fade_sensitivity.csv`, `session_reversal_summary.csv`).

## Prueba específica: arbitraje estadístico BTC/ETH (06-11-2026)

Probé 18 configuraciones de pair trading sobre perps BTCUSDT/ETHUSDT en velas de 4h (2020–05 nov 2026): hedge ratio fijo estimado solo en 2020–2022 o beta móvil; ventanas 30/90/180 días; entrada al alejarse 1,5/2/2,5 desviaciones y salida al volver a 0,5. La señal se ejecuta en la apertura siguiente; la cartera tiene exposición bruta total 1x, incluye funding observado y cobra 5 pb por notional operado en cada pata, con estrés a 10 pb. No incluí spread, deslizamiento ni liquidaciones específicas por exchange/margen.

**Resultado: no encontré una relación BTC/ETH estable que haga funcionar esta reversión.** El test Engle–Granger del spread estimado en entrenamiento dio ADF t = -1,03, lejos del crítico aproximado de 5% (≈ -3,34), así que no hay evidencia de cointegración en esa muestra. La configuración más rentable en validación fue la beta móvil de 90 días, entrada 2,5σ: en 2023–nov 2026 hizo 2,0% CAGR, Sharpe 0,29 y drawdown -12,2%; duplicar fees bajó a 1,0% CAGR y Sharpe 0,16. Pero en entrenamiento perdió 7,8% anualizado (Sharpe -0,38), fue negativa en 2026 YTD y quedó muy por debajo de BTC/ETH pasivo en retorno. La configuración elegida por entrenamiento (beta fija 180d de z-score, entrada 2σ) perdió 7,9% anual en validación. El mejor resultado posterior es débil y no es una señal convincente: parece más compatible con variación de régimen que con alpha robusta.

**Lectura:** queda descartado como candidato operativo por ahora. Esto solo descarta estas reglas de reversión de spread, no todo stat arb: harían falta una relación mejor justificada (pares/universo más amplio, neutralización de beta), costos de ejecución reales y validación nueva. Script: `btc_eth_stat_arb.py`; resultados: `btc_eth_stat_arb_summary.csv`.

## Cartera compuesta estilo quant: tendencia + momentum relativo + carry (06-11-2026)

Probé una cartera estilo multi-sleeve: tendencia temporal sobre BTC/ETH/BNB/SOL (votos de momentum 20/60/120, 30/90/180 o 60/120/240 días; long/short o long/efectivo; pesos inversos a volatilidad), momentum relativo semanal long top 1/short bottom 1 (30/90/180 días) y carry spot-largo/perpetuo-corto. El carry quedó restringido a BTC/ETH porque BNB/SOL habían sido débiles en pruebas previas. Promedié modelos de cada sleeve entre varios parámetros (“parameter bagging”) y probé 486 mezclas por nivel de comisión, con pesos definidos antes de mirar la validación. Señal al cierre, ejecución desde el día siguiente, funding y fees taker incluidos; estrés con fees duplicadas. Marcas diarias aproximadas desde las observaciones de funding UTC; sin spread, deslizamiento ni liquidación exacta; el universo actual tiene sesgo de supervivencia.

La mezcla bagged elegida **solo por Sharpe de entrenamiento 2020–2022**, entre mezclas de dos/tres sleeves, fue 60% tendencia + 40% carry BTC/ETH (sin momentum relativo). En validación 2023–05 nov 2026: CAGR 13,0%, Sharpe 0,71, volatilidad 20,0%, drawdown -26,2%. Con comisiones duplicadas: CAGR 10,3%, Sharpe 0,59, drawdown -27,2%. En 2026 YTD rindió 1,1%, Sharpe 0,15. BTC spot, en el mismo test: 48,5% CAGR, Sharpe 1,11 y drawdown -53,3%. La mezcla redujo a la mitad la caída histórica, pero tuvo menor retorno y menor Sharpe que BTC; eso es control de riesgo, no alpha superior.

El walk-forward anual de 3 años de entrenamiento eligió esa misma mezcla cada año de 2023 a 2026, con CAGR agregado 13,0%, Sharpe 0,71 y drawdown -26,2%. El sleeve de momentum relativo dio pérdidas en entrenamiento y validación, por eso no quedó en el mix elegido. Una primera corrida exploratoria tenía carry mal normalizado entre monedas y se descartó; la versión reportada normaliza exposición, limita el carry a BTC/ETH y no usa más de 1x bruto. También medí una selección retrospectiva con las mismas fechas de validación, pero no la considero resultado válido.

**Conclusión:** hay una candidata modesta para paper trading si el objetivo principal es suavizar la exposición y las caídas. No la llamaría “super estrategia”: no supera BTC en rentabilidad ajustada al riesgo, 2026 fue flojo y faltan costos/fills reales. Scripts/salidas: `ensemble_quant_backtest.py`, `ensemble_quant_summary.csv`, `ensemble_quant_walkforward_selections.csv`, `ensemble_quant_walkforward_summary.csv`, `ensemble_quant_bag_walkforward_selections.csv` y `ensemble_quant_bag_walkforward_summary.csv`.
