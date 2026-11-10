"use client";

import * as React from "react";
import { Dialog, Transition } from "@headlessui/react";
import {
  CheckCircleIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  EnvelopeIcon,
  InformationCircleIcon,
  MagnifyingGlassIcon,
  QuestionMarkCircleIcon,
  XCircleIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import { dispatchHelpOnboardingPrompt } from "@/lib/help-onboarding-events";
import { useComposerStore } from "@/lib/stores/composer-store";
import { cn } from "@/lib/utils";
import { type VistaPredefinida } from "./help-onboarding-content";
import { IconoAyuda } from "./IconoAyuda";
import { useGuiaAyuda } from "./useGuiaAyuda";
import { useToolSuggestions, type ToolSuggestion } from "./useToolSuggestions";
import { useVistasPredefinidas } from "./useVistasPredefinidas";

const SUPPORT_EMAIL = "support@saptiva.com";
const SIN_CATEGORIA = "otras";

function normalizeSearchValue(value: string): string {
  return value.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").trim();
}

function coincide(
  item: { titulo: string; descripcion?: string; prompt: string },
  consulta: string,
): boolean {
  if (!consulta) return true;
  return normalizeSearchValue(
    `${item.titulo} ${item.descripcion ?? ""} ${item.prompt}`,
  ).includes(consulta);
}

function etiquetaCategoria(categoria: string): string {
  return categoria.charAt(0).toUpperCase() + categoria.slice(1);
}

/** Agrupa las sugerencias por categoría, en el orden en que llegan. */
function porCategoria(
  sugerencias: ToolSuggestion[],
): Array<[string, ToolSuggestion[]]> {
  const grupos = new Map<string, ToolSuggestion[]>();
  sugerencias.forEach((s) => {
    const clave = (s.categoria || SIN_CATEGORIA).trim().toLowerCase();
    grupos.set(clave, [...(grupos.get(clave) ?? []), s]);
  });
  return Array.from(grupos.entries());
}

/**
 * Avisa cuando el diálogo ya se desmontó. headlessui devuelve el foco al botón
 * "?" en una microtarea al desmontar; el aviso va en una tarea posterior para
 * que el compositor tome el foco después (QA, P2.7: con el foco en
 * "?", un Enter volvía a abrir la ayuda en vez de enviar).
 */
function AlDesmontar({ hacer }: { hacer: () => void }) {
  const hacerRef = React.useRef(hacer);
  hacerRef.current = hacer;
  React.useEffect(
    () => () => {
      window.setTimeout(() => hacerRef.current(), 0);
    },
    [],
  );
  return null;
}

function TituloSeccion({
  titulo,
  detalle,
}: {
  titulo: string;
  detalle: string;
}) {
  return (
    <div className="mb-2 flex items-baseline justify-between gap-3">
      <h3 className="text-sm font-semibold text-foreground">{titulo}</h3>
      <span className="text-xs text-muted">{detalle}</span>
    </div>
  );
}

/**
 * Ayuda del chat: vistas predefinidas (resúmenes de un clic, feedback round 1
 * de QA, punto 14), las preguntas sugeridas del plugin agrupadas por
 * categoría (antes chips bajo el compositor; Equipo, 2026-10-19) y la guía
 * rápida, también del plugin (QA, P2.2). Elegir una vista o pregunta
 * la escribe en el compositor; el usuario la envía.
 *
 * Abierta o cerrada vive en el store del compositor, por `ubicacion` (hay un
 * botón por layout): al crear un chat nuevo la vista se vuelve a montar y la
 * ayuda se cerraba en las manos del usuario (P2.7 del reporte de QA).
 */
export function HelpOnboardingMenu({
  ubicacion = "encabezado",
}: {
  ubicacion?: string;
}) {
  const isOpen = useComposerStore((s) => s.ayudaAbierta === ubicacion);
  const setIsOpen = React.useCallback(
    (siguiente: boolean | ((actual: boolean) => boolean)) => {
      const store = useComposerStore.getState();
      const actual = store.ayudaAbierta === ubicacion;
      const abrir =
        typeof siguiente === "function" ? siguiente(actual) : siguiente;
      if (abrir) store.abrirAyuda(ubicacion);
      else if (actual) store.cerrarAyuda();
    },
    [ubicacion],
  );
  const [query, setQuery] = React.useState("");
  const [isGuideOpen, setIsGuideOpen] = React.useState(false);
  const searchInputRef = React.useRef<HTMLInputElement>(null);
  const menuId = React.useId();
  const { vistas, cargando } = useVistasPredefinidas(isOpen);
  const sugerencias = useToolSuggestions(isOpen);
  const guia = useGuiaAyuda(isOpen);
  const hayGuia = guia.puedes.length > 0 || guia.no_tiene.length > 0;

  React.useEffect(() => {
    if (!isOpen) return;
    const timer = window.setTimeout(() => {
      searchInputRef.current?.focus();
    }, 80);
    return () => {
      window.clearTimeout(timer);
    };
  }, [isOpen]);

  const closeMenu = React.useCallback(() => {
    setIsOpen(false);
    setQuery("");
    setIsGuideOpen(false);
  }, [setIsOpen]);

  const handleTriggerClick = React.useCallback(() => {
    const next = !isOpen;
    if (!next) {
      setQuery("");
      setIsGuideOpen(false);
    }
    setIsOpen(next);
  }, [isOpen, setIsOpen]);

  const normalizedQuery = React.useMemo(
    () => normalizeSearchValue(query),
    [query],
  );

  const vistasFiltradas = React.useMemo(
    () => vistas.filter((v) => coincide(v, normalizedQuery)),
    [vistas, normalizedQuery],
  );

  const gruposSugerencias = React.useMemo(
    () => porCategoria(sugerencias.filter((s) => coincide(s, normalizedQuery))),
    [sugerencias, normalizedQuery],
  );

  // El prompt elegido se manda al chat cuando el diálogo termina de cerrar
  // (ver AlDesmontar).
  const promptElegido = React.useRef<string | null>(null);
  const usarPrompt = React.useCallback(
    (prompt: string) => {
      // Al store en seguida: si el compositor se está montando en este
      // instante (chat nuevo), lo toma al montar. El evento, que además deja
      // el foco en el compositor, sale cuando el diálogo se desmonta.
      useComposerStore.getState().fijarTexto(prompt, null);
      promptElegido.current = prompt;
      closeMenu();
    },
    [closeMenu],
  );
  const mandarPromptElegido = React.useCallback(() => {
    const prompt = promptElegido.current;
    promptElegido.current = null;
    if (prompt) dispatchHelpOnboardingPrompt(prompt);
  }, []);

  const sinResultados =
    !cargando && vistasFiltradas.length === 0 && gruposSugerencias.length === 0;

  return (
    <div className="relative">
      <button
        type="button"
        data-testid="help-onboarding-trigger"
        onClick={handleTriggerClick}
        className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-border bg-surface text-sm font-semibold text-muted transition-all hover:border-primary/50 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
        aria-label="Abrir vistas predefinidas y guía"
        aria-expanded={isOpen}
        aria-haspopup="dialog"
        aria-controls={menuId}
        title="Vistas, preguntas sugeridas y guía"
      >
        <QuestionMarkCircleIcon className="h-5 w-5" />
      </button>

      <Transition.Root show={isOpen} as={React.Fragment}>
        <Dialog as="div" className="relative z-[70]" onClose={closeMenu}>
          <Transition.Child
            as={React.Fragment}
            enter="ease-out duration-200"
            enterFrom="opacity-0"
            enterTo="opacity-100"
            leave="ease-in duration-150"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <div
              className="fixed inset-0 bg-black/50 backdrop-blur-sm"
              data-testid="help-onboarding-overlay"
            />
          </Transition.Child>

          <div className="fixed inset-0 overflow-y-auto p-3 sm:p-5">
            <div className="flex min-h-full items-center justify-center">
              <Transition.Child
                as={React.Fragment}
                enter="ease-out duration-200"
                enterFrom="opacity-0 translate-y-3 sm:translate-y-0 sm:scale-95"
                enterTo="opacity-100 translate-y-0 sm:scale-100"
                leave="ease-in duration-150"
                leaveFrom="opacity-100 translate-y-0 sm:scale-100"
                leaveTo="opacity-0 translate-y-3 sm:translate-y-0 sm:scale-95"
              >
                <Dialog.Panel
                  id={menuId}
                  data-testid="help-onboarding-menu"
                  className="w-full max-w-3xl overflow-hidden rounded-2xl border border-border bg-surface shadow-card"
                >
                  <AlDesmontar hacer={mandarPromptElegido} />
                  <div className="flex items-start justify-between gap-3 border-b border-border/70 px-4 py-4 sm:px-5">
                    <div>
                      <Dialog.Title className="text-base font-semibold text-foreground sm:text-lg">
                        ¿Qué puedo preguntar?
                      </Dialog.Title>
                      <p className="mt-1 text-xs text-muted sm:text-sm">
                        Elige una vista o una pregunta: se escribe en el chat y
                        tú la envías.
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={closeMenu}
                      className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border text-muted transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
                      aria-label="Cerrar"
                    >
                      <XMarkIcon className="h-4 w-4" />
                    </button>
                  </div>

                  <div className="max-h-[min(82vh,48rem)] space-y-6 overflow-y-auto thin-scroll px-4 py-4 sm:px-5">
                    <div className="flex items-center gap-2 rounded-xl border border-border bg-background/60 px-3 py-2.5">
                      <MagnifyingGlassIcon className="h-4 w-4 text-muted" />
                      <input
                        ref={searchInputRef}
                        value={query}
                        onChange={(event) => setQuery(event.target.value)}
                        placeholder="Buscar vista o pregunta..."
                        className="w-full border-0 bg-transparent text-sm text-foreground placeholder:text-muted focus:outline-none"
                        data-testid="help-onboarding-search"
                      />
                    </div>

                    {vistasFiltradas.length > 0 ? (
                      <section>
                        <TituloSeccion
                          titulo="Vistas predefinidas"
                          detalle="Resúmenes de un clic"
                        />
                        <div className="grid gap-2 sm:grid-cols-2">
                          {vistasFiltradas.map((vista: VistaPredefinida) => (
                            <button
                              key={vista.id}
                              type="button"
                              onClick={() => usarPrompt(vista.prompt)}
                              data-testid={`help-onboarding-prompt-${vista.id}`}
                              className="group flex h-full items-start gap-3 rounded-xl border border-border bg-background/70 px-3 py-3 text-left transition-colors hover:border-primary/40 hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
                            >
                              <span className="inline-flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                                <IconoAyuda
                                  icono={vista.icono}
                                  className="h-4 w-4"
                                />
                              </span>
                              <span className="min-w-0">
                                <span className="block text-sm font-medium leading-tight text-foreground">
                                  {vista.titulo}
                                </span>
                                {vista.descripcion && (
                                  <span className="mt-1 block text-xs leading-snug text-muted">
                                    {vista.descripcion}
                                  </span>
                                )}
                              </span>
                            </button>
                          ))}
                        </div>
                      </section>
                    ) : null}

                    {gruposSugerencias.length > 0 ? (
                      <section>
                        <TituloSeccion
                          titulo="Preguntas sugeridas"
                          detalle="Ejemplos para empezar"
                        />
                        <div className="space-y-4">
                          {gruposSugerencias.map(([categoria, items]) => (
                            <div key={categoria}>
                              <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
                                {etiquetaCategoria(categoria)}
                              </h4>
                              <ul className="divide-y divide-border/60 overflow-hidden rounded-xl border border-border">
                                {items.map((s) => (
                                  <li key={s.id}>
                                    <button
                                      type="button"
                                      onClick={() => usarPrompt(s.prompt)}
                                      data-testid={`help-onboarding-sugerencia-${s.id}`}
                                      title={s.prompt}
                                      className="group flex w-full items-center gap-3 bg-background/70 px-3 py-2.5 text-left transition-colors hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary/60"
                                    >
                                      <IconoAyuda
                                        icono={s.icono}
                                        className="h-4 w-4 flex-shrink-0 text-primary"
                                      />
                                      <span className="min-w-0 flex-1">
                                        <span className="block text-sm font-medium text-foreground">
                                          {s.titulo}
                                        </span>
                                        <span className="block truncate text-xs text-muted">
                                          {s.descripcion || s.prompt}
                                        </span>
                                      </span>
                                      <ChevronRightIcon
                                        aria-hidden="true"
                                        className="h-4 w-4 flex-shrink-0 text-muted transition-transform group-hover:translate-x-0.5"
                                      />
                                    </button>
                                  </li>
                                ))}
                              </ul>
                            </div>
                          ))}
                        </div>
                      </section>
                    ) : null}

                    {sinResultados ? (
                      <div
                        className="rounded-xl border border-dashed border-border bg-background/50 px-4 py-8 text-center text-sm text-muted"
                        data-testid="help-onboarding-no-results"
                      >
                        {normalizedQuery
                          ? "No se encontraron vistas ni preguntas para esta búsqueda."
                          : "No hay vistas ni preguntas disponibles por ahora. Puedes preguntar directamente en el chat."}
                      </div>
                    ) : null}

                    {!normalizedQuery && hayGuia ? (
                      <section className="rounded-xl border border-primary/20 bg-primary/5">
                        <button
                          type="button"
                          onClick={() => setIsGuideOpen((current) => !current)}
                          className="flex w-full items-center justify-between gap-2 px-4 py-3 text-left"
                          data-testid="help-onboarding-guide-toggle"
                          aria-expanded={isGuideOpen}
                        >
                          <span className="inline-flex items-center gap-2 text-sm font-semibold text-foreground">
                            <InformationCircleIcon className="h-4 w-4 text-primary" />
                            Guía rápida: qué tiene y qué no tiene
                          </span>
                          <ChevronDownIcon
                            className={cn(
                              "h-4 w-4 text-muted transition-transform",
                              isGuideOpen ? "rotate-180" : "rotate-0",
                            )}
                          />
                        </button>

                        <Transition
                          as={React.Fragment}
                          show={isGuideOpen}
                          enter="transition duration-200 ease-out"
                          enterFrom="opacity-0 -translate-y-1"
                          enterTo="opacity-100 translate-y-0"
                          leave="transition duration-150 ease-in"
                          leaveFrom="opacity-100 translate-y-0"
                          leaveTo="opacity-0 -translate-y-1"
                        >
                          <div className="border-t border-primary/15 px-4 pb-4 pt-3">
                            <div className="grid gap-3 md:grid-cols-2">
                              <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-3">
                                <h4 className="mb-2 inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-emerald-600 dark:text-emerald-400">
                                  <CheckCircleIcon className="h-4 w-4" />
                                  Lo que puedes hacer
                                </h4>
                                <ul className="space-y-1 text-xs leading-relaxed text-muted">
                                  {guia.puedes.map((item) => (
                                    <li key={item}>{item}</li>
                                  ))}
                                </ul>
                              </div>

                              <div className="rounded-lg border border-rose-500/20 bg-rose-500/10 p-3">
                                <h4 className="mb-2 inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-rose-600 dark:text-rose-400">
                                  <XCircleIcon className="h-4 w-4" />
                                  Lo que no tiene
                                </h4>
                                <ul className="space-y-1 text-xs leading-relaxed text-muted">
                                  {guia.no_tiene.map((item) => (
                                    <li key={item}>{item}</li>
                                  ))}
                                </ul>
                              </div>
                            </div>
                          </div>
                        </Transition>
                      </section>
                    ) : null}

                    <div className="inline-flex flex-wrap items-center gap-2 rounded-lg border border-border bg-background/60 px-3 py-2 text-xs text-muted">
                      <EnvelopeIcon className="h-4 w-4" />
                      <span>¿Necesitas ayuda?</span>
                      <a
                        href={`mailto:${SUPPORT_EMAIL}`}
                        className="font-semibold text-primary hover:underline"
                      >
                        {SUPPORT_EMAIL}
                      </a>
                    </div>
                  </div>
                </Dialog.Panel>
              </Transition.Child>
            </div>
          </div>
        </Dialog>
      </Transition.Root>
    </div>
  );
}

export default HelpOnboardingMenu;
