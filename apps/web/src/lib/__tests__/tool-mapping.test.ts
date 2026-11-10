import {
  createDefaultToolsState,
  defaultToolKeysFromEnv,
  isLockedTool,
  normalizeToolsState,
  toolsConChipEnComposer,
} from "../tool-mapping";

describe("createDefaultToolsState", () => {
  it("arranca con retail_advisor prendida (default-on de la POC)", () => {
    // Sin la tool, el LLM responde consultas de datos con cifras inventadas
    // (reproducido en vivo 2026-07-13); el default-on cierra ese flanco.
    const state = createDefaultToolsState();
    expect(state.retail_advisor).toBe(true);
  });

  it("el resto de tools arranca apagado", () => {
    const state = createDefaultToolsState();
    const others = Object.entries(state).filter(
      ([key]) => key !== "retail_advisor",
    );
    expect(others.length).toBeGreaterThan(0);
    others.forEach(([, enabled]) => expect(enabled).toBe(false));
  });

  it("extraToolKeys entran apagadas sin pisar el default-on", () => {
    const state = createDefaultToolsState(["viz_tool"]);
    expect(state.viz_tool).toBe(false);
    expect(state.retail_advisor).toBe(true);
  });
});

describe("normalizeToolsState", () => {
  it("la herramienta de datos no se apaga aunque el estado guardado diga false", () => {
    // feedback round 1 (2026-10-16, punto 10): con el chip apagado
    // el chat contestaba "la herramienta está desactivada, actívala desde el
    // compositor". En Industry Advisor la herramienta de datos va siempre.
    const state = normalizeToolsState({ retail_advisor: false });
    expect(state.retail_advisor).toBe(true);
  });

  it("sin valor explícito conserva el default-on", () => {
    const state = normalizeToolsState({ web_search: true });
    expect(state.retail_advisor).toBe(true);
    expect(state.web_search).toBe(true);
  });

  it("las demás tools respetan el apagado del usuario", () => {
    const state = normalizeToolsState({ web_search: false });
    expect(state.web_search).toBe(false);
  });
});

describe("isLockedTool", () => {
  it("la herramienta de datos está bloqueada; las demás no", () => {
    expect(isLockedTool("retail-advisor")).toBe(true);
    expect(isLockedTool("retail_advisor")).toBe(true);
    expect(isLockedTool("web-search")).toBe(false);
    expect(isLockedTool("web_search")).toBe(false);
  });
});

describe("defaultToolKeysFromEnv", () => {
  // La POC fija la herramienta por entorno (NEXT_PUBLIC_DEFAULT_TOOLS); el
  // chip del compositor desaparece y la tool va encendida y bloqueada.
  it("lee la lista separada por comas, con espacios y guiones", () => {
    const keys = defaultToolKeysFromEnv("retail-advisor, web_search ,");
    expect(Array.from(keys)).toEqual(["retail_advisor", "web_search"]);
  });

  it("vacía o sin definir cae al default de los feature flags", () => {
    expect(defaultToolKeysFromEnv(undefined).has("retail_advisor")).toBe(true);
    expect(defaultToolKeysFromEnv("   ").has("retail_advisor")).toBe(true);
  });

  it("ignora keys que no existen", () => {
    expect(
      Array.from(defaultToolKeysFromEnv("no_existe,retail_advisor")),
    ).toEqual(["retail_advisor"]);
  });
});

describe("toolsConChipEnComposer", () => {
  it("las bloqueadas no pintan chip; las demás sí", () => {
    expect(toolsConChipEnComposer(["retail-advisor", "web-search"])).toEqual([
      "web-search",
    ]);
  });
});
