# Lab 13 (Extra): El carrito revisado por pruebas



Carrito de compras en Django con dinero exacto, existencias y cupones, revisado con pruebas, una auditoría sin pantalla y una compuerta de aceptación. El laboratorio tiene dos partes: escribir el carrito del equipo y revisar y arreglar el que escribió una IA.

## Resultado

| Implementación | Pruebas (de 67) | Compuerta | Código de salida |
|---|---|---|---|
| Mi carrito (`shop/cart_team.py`) | 67 pasan | aceptar | 0 |
| Carrito de la IA, original (`shop/cart_ai.py`) | 49 pasan, 18 fallan | rechazar | 1 |
| Carrito de la IA, arreglado | 67 pasan | aceptar | 0 |

## Reglas de la tienda

| Regla | Qué dice |
|---|---|
| Dinero | Todo se calcula con `Decimal`, nunca con `float`. La mitad se redondea hacia arriba: 0,005 pasa a 0,01. |
| Precio | Lo decide el catálogo del servidor. La petición del cliente nunca trae el precio. |
| Existencias | Lo que ya hay en el carrito más lo que se agrega no puede superar el stock. Al pagar se vuelve a comprobar y el stock nunca baja de cero. |
| Cupón | Solo hay uno por carrito. `BIENVENIDA10` descuenta el 10 % del subtotal y `MENOS20` descuenta S/ 20 sin pasar del subtotal. Aplicar otro cupón, o el mismo, lo reemplaza. |

## Parte 1: el carrito del equipo

Se implementó `shop/cart_team.py`, un método por vez, guiado por las pruebas:

| Método | Qué hace |
|---|---|
| `add` | Valida cantidad (entero ≥ 1, no `bool`) y producto, y cuenta lo ya agregado contra el stock antes de modificar nada |
| `remove` | Borra la línea cuando la cantidad llega a cero; nunca deja cantidades negativas |
| `lines` | Una línea por producto, con nombre y precio tomados del catálogo |
| `checkout` | Revalida todas las líneas antes de restar ninguna, baja el stock, vacía el carrito y devuelve el resumen |
| `subtotal`, `discount`, `igv`, `total`, `summary` | Todo en `Decimal` con el helper `money`; el total es la suma de partes ya redondeadas |
| `apply_coupon` | Normaliza el código, valida y reemplaza el cupón anterior |
| `add_from_payload` | Traduce el cuerpo de la API a `add`; rechaza cuerpos inválidos y nunca lee el precio |

Cálculo a mano de verificación (un mousepad `PAD-01` a S/ 8,45 con `BIENVENIDA10`): subtotal 8,45, descuento 0,85, IGV 1,37, total 8,97.

## Parte 2: los cinco fallos de la IA

`python manage.py duelo --modo ai` mostró 18 pruebas fallando, que se reducen a cinco defectos (líneas del commit original `d5e37`):

| # | Fallo | Línea original | Prueba que lo detecta | Causa |
|---|---|---|---|---|
| 1 | Redondeo con flotantes | `cart_ai.py:84` | `test_igv_rounds_half_up` | Dinero en `float` y `round`; 0,845 se guarda como 0,84499… |
| 2 | Precio tomado del cliente | `cart_ai.py:53` y `:139` | `test_the_price_comes_from_the_catalog_not_from_the_client` | Guarda el `price` de la petición. **Fallo de seguridad, solo visible con la API** |
| 3 | Existencias sin contar lo ya agregado | `cart_ai.py:50` | `test_the_stock_counts_what_is_already_in_the_cart` | Compara solo la cantidad nueva con el stock |
| 4 | Cantidad negativa al quitar | `cart_ai.py:63-64` | `test_remove_more_than_there_is_never_leaves_a_negative_quantity` | Resta sin acotar y solo borra la línea si queda en 0 |
| 5 | Descuento acumulado dos veces | `cart_ai.py:81` y `:89` | `test_applying_the_same_coupon_twice_discounts_once` | Guarda los cupones en una lista y suma todos |

Defecto adicional: `checkout` no volvía a comprobar las existencias, lo que dejaba el stock negativo.

## Parte 3: arreglar `cart_ai.py`

Un fallo cada vez, midiendo las pruebas que fallaban antes y después (`SHOP_MODE=ai`):

| Arreglo | Método | Fallaban antes | Después |
|---|---|---|---|
| Precio del cliente (parte 1) | `add_from_payload` | 18 | 16 |
| Precio del cliente (parte 2) | `add` | 16 | 16 |
| Existencias | `add` | 16 | 12 |
| Cantidad negativa | `remove` | 12 | 10 |
| Cupón doble | `apply_coupon` | 10 | 7 |
| `checkout` sin revalidar | `checkout` | 7 | 5 |
| Redondeo | `igv`, `total`, `discount` | 5 | 0 |
| Redondeo (parte final) | `subtotal` | 0 | 0 |
| Limpieza de código muerto con `float` | `_subtotal`, `_discount`, `_money`, `IGV` | 0 | 0 |

## Auditoría y compuerta

**Auditoría** (`audit_cart`): recalcula cada carrito declarado en `carts/*.json` desde el catálogo y la fórmula de referencia. Sobre el código original de la IA, solo `01-correcto.json` quedó sin hallazgos.

- `TOTAL_MISMATCH`: el carrito **declara** mal.
- `REPLAY_MISMATCH`: la implementación **calcula** mal.
- `REPLAY_REJECTED`: la implementación se niega a reconstruir el carrito. Para los carritos 03 y 04 es la respuesta correcta.

**Compuerta** (`gate`): combina las 67 pruebas y los seis carritos en un veredicto con código de salida (0 aceptar, 1 rechazar) y una salida `--json` para que la lea un agente. Las dos partes son necesarias: el replay de la auditoría no detecta el precio del cliente porque nunca envía el campo `price`, y ese fallo solo lo detectan las pruebas de la API.

**Límite de la auditoría:** avisa después de que el cobro ocurrió. La regla en el servidor lo impide antes.

## Uso de un agente bajo `AGENTS.md`

Los arreglos de `cart_ai.py` se hicieron con OpenCode bajo el contrato de `AGENTS.md`: un método por turno, solo el archivo del carrito y sus pruebas, sin `git commit` ni `git push` por parte del agente, y la compuerta como criterio de terminado. Cada diff se revisó con `git diff` y se aplicaron cuatro preguntas de revisión:

1. ¿Todo el dinero es `Decimal` de principio a fin?
2. ¿El servidor es la única fuente del precio?
3. ¿Cada regla de cantidad y existencias se cumple con cualquier secuencia de acciones?
4. ¿Repetir una acción (doble clic, reintento) da el mismo resultado?

**Caso destacado:** tras el turno de `discount` la compuerta dio `aceptar` con 67 de 67, pero la pregunta 1 mostró que `subtotal()` seguía calculando con `float`. El diff se aceptó, pero no el «terminado», y se hicieron dos turnos más (`subtotal` y limpieza). La compuerta comprueba lo que alguien pensó probar; las preguntas revisan lo que el código es.

## Cómo ejecutar

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_shop

python manage.py test                    # 67 pruebas, mi carrito
$env:PYTHONIOENCODING = "utf-8"          # necesario en Windows para duelo y gate
python manage.py duelo                   # mi carrito contra el de la IA
python manage.py gate                    # compuerta, mi carrito
$env:SHOP_MODE = "ai"                    # ejecutar contra el carrito de la IA
python manage.py gate --modo ai
python manage.py audit_cart $files --catalogo-fijo --replay
```

`$files` es la lista de archivos de `carts/` (en PowerShell, `Get-ChildItem carts\*.json | ForEach-Object { "carts/" + $_.Name }`).

## Lecciones

- Las pruebas funcionan como oráculo: las mismas 67 comparan dos implementaciones.
- Un `float` no puede guardar 0,845; el dinero va en `Decimal` con redondeo hacia arriba en la mitad.
- El cliente controla lo que envía, así que el servidor decide el precio y repite las comprobaciones críticas.
- Una compuerta en verde no sustituye la revisión del código.

## Archivos modificados

- `shop/cart_team.py`: carrito del equipo.
- `shop/cart_ai.py`: carrito de la IA, arreglado.
- `INFORME-LAB13.md`: este informe.