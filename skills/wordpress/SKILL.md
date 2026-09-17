---
name: wordpress
description: Convenzioni, hook e sicurezza per plugin e temi WordPress
---

# WordPress: come si scrive codice qui

## La trinità della sicurezza

Ogni volta che il codice tocca l'esterno servono tutte e tre, non una a scelta:

1. **Capability** prima dell'azione: `current_user_can('manage_options')`, mai
   `is_admin()`, che dice solo in quale area sei.
2. **Nonce** su ogni form e ogni azione che cambia stato: `wp_nonce_field()` in uscita,
   `check_admin_referer()` o `wp_verify_nonce()` in ingresso.
3. **Sanitizzazione in ingresso, escape in uscita**: `sanitize_text_field()`,
   `absint()`, `sanitize_email()` quando il dato entra; `esc_html()`, `esc_attr()`,
   `esc_url()`, `wp_kses_post()` quando esce. L'escape si fa al momento della stampa, non
   quando il dato viene salvato: è l'unico punto in cui sai in che contesto finisce.

Le query con parametri passano sempre da `$wpdb->prepare()`. Nessuna eccezione, nemmeno
per un intero che «tanto viene da noi».

## Hook

- Registra con la priorità di default (10) finché non hai una ragione per cambiarla, e
  quando la cambi scrivi il perché in un commento.
- Dichiara il numero di argomenti: `add_action('save_post', 'fn', 10, 3)`. Ometterlo è la
  causa più comune di argomenti mancanti.
- Non agganciare mai a `init` ciò che può stare in un hook più tardivo e più specifico.
- Le funzioni agganciate hanno un prefisso di progetto: WordPress è uno spazio dei nomi
  globale condiviso con centinaia di plugin.

## Database e performance

- `WP_Query` invece di SQL diretto quando è possibile; `'no_found_rows' => true` se non
  serve la paginazione, `'fields' => 'ids'` se servono solo gli ID.
- Mai `posts_per_page => -1` su dati che possono crescere.
- La cache degli oggetti (`wp_cache_get`/`wp_cache_set`) per i risultati costosi, i
  transient per ciò che deve sopravvivere alla richiesta.
- Le opzioni autoload: `add_option($name, $value, '', 'no')` per quelle che non servono a
  ogni caricamento di pagina.

## Struttura di un plugin

- Intestazione completa nel file principale, `Requires PHP` e `Requires at least`
  compresi.
- `defined('ABSPATH') || exit;` in cima a ogni file PHP.
- Attivazione, disattivazione e disinstallazione gestite: `register_activation_hook`,
  `register_deactivation_hook`, `uninstall.php`. Un plugin che disinstallato lascia
  tabelle e opzioni è un plugin non finito.
- Traduzioni: `__()` ed `_e()` con il text domain del plugin, caricato su
  `init` con `load_plugin_textdomain()`.

## Errori ricorrenti da non ripetere

- Usare `$_POST` senza nonce e senza capability perché «è un'area admin».
- Scrivere `esc_html` sul dato salvato invece che sul dato stampato.
- Enqueue di script e stili fuori da `wp_enqueue_scripts` o `admin_enqueue_scripts`.
- Modificare direttamente i file del core o di un tema di terze parti invece di usare un
  child theme o un filtro.
