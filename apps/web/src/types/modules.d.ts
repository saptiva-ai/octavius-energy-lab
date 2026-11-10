declare module "plotly.js-dist-min" {
  // Mismo API que 'plotly.js' (bundle standalone pre-compilado, sin deps de tipos propias).
  export * from "plotly.js";
  import PlotlyStatic from "plotly.js";
  export default PlotlyStatic;
}

declare module "react-plotly.js" {
  import * as Plotly from "plotly.js";
  import * as React from "react";

  interface PlotParams {
    data: Plotly.Data[];
    layout?: Partial<Plotly.Layout>;
    config?: Partial<Plotly.Config>;
    style?: React.CSSProperties;
    className?: string;
    useResizeHandler?: boolean;
    onInitialized?: (figure: Plotly.Figure, graphDiv: HTMLElement) => void;
    onUpdate?: (figure: Plotly.Figure, graphDiv: HTMLElement) => void;
    onPurge?: (figure: Plotly.Figure, graphDiv: HTMLElement) => void;
    onError?: (error: Error) => void;
  }

  const Plot: React.ComponentType<PlotParams>;
  export default Plot;
}
