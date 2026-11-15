import type { MDXComponents } from "mdx/types";
import { A, Callout, Card, Cards, H2, H3, H4, Pre, Step, Steps, Table, Tool } from "@/components/docs/mdx";
import { DocHeader } from "@/components/docs/shell";

const components: MDXComponents = {
  h2: H2,
  h3: H3,
  h4: H4,
  a: A,
  pre: Pre,
  table: Table,
  Callout,
  Steps,
  Step,
  Cards,
  Card,
  Tool,
  DocHeader,
};

export function useMDXComponents(): MDXComponents {
  return components;
}
