import { Body, Container, Head, Html, Img, Preview, Section, Text } from "@react-email/components";
import type { ReactNode } from "react";

export const emailBrand = {
  paper: "#fafbf8",
  pine: "#172b26",
  muted: "#56635e",
  border: "#dce0da",
  darkMuted: "#cfdccf",
  darkBorder: "#56635e",
  darkButton: "#b6e87a",
  logo: "https://cuadrao-web-staging.onrender.com/icons/cuadrao-192.png",
} as const;

export const paragraphStyle = { margin: "0 0 20px", fontSize: "16px", lineHeight: "26px" };

export function EmailLayout({ children, preview }: { children: ReactNode; preview: string }) {
  return <Html lang="es">
    <Head>
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <meta name="color-scheme" content="light dark" />
      <meta name="supported-color-schemes" content="light dark" />
      <style>{`
        @media (prefers-color-scheme: dark) {
          .cuadrao-body, .cuadrao-container { background-color: ${emailBrand.pine} !important; color: ${emailBrand.paper} !important; }
          .cuadrao-container, .cuadrao-footer { border-color: ${emailBrand.darkBorder} !important; }
          .cuadrao-copy { color: ${emailBrand.paper} !important; }
          .cuadrao-muted { color: ${emailBrand.darkMuted} !important; }
          .cuadrao-button { background-color: ${emailBrand.darkButton} !important; color: ${emailBrand.pine} !important; }
        }
        [data-ogsc] .cuadrao-body, [data-ogsc] .cuadrao-container { background-color: ${emailBrand.pine} !important; color: ${emailBrand.paper} !important; }
        [data-ogsc] .cuadrao-container, [data-ogsc] .cuadrao-footer { border-color: ${emailBrand.darkBorder} !important; }
        [data-ogsc] .cuadrao-copy { color: ${emailBrand.paper} !important; }
        [data-ogsc] .cuadrao-muted { color: ${emailBrand.darkMuted} !important; }
        [data-ogsc] .cuadrao-button { background-color: ${emailBrand.darkButton} !important; color: ${emailBrand.pine} !important; }
      `}</style>
    </Head>
    <Body className="cuadrao-body" style={{ margin: "0", padding: "32px 16px", backgroundColor: emailBrand.paper, color: emailBrand.pine, fontFamily: "Arial, Helvetica, sans-serif" }}>
      <Preview>{preview}</Preview>
      <Container className="cuadrao-container" style={{ maxWidth: "560px", backgroundColor: emailBrand.paper, border: `1px solid ${emailBrand.border}`, borderRadius: "16px" }}>
        <Section style={{ padding: "32px 32px 20px" }}>
          <Img src={emailBrand.logo} width="48" height="48" alt="Cuadrao" style={{ display: "block", border: "0", marginBottom: "28px" }} />
          {children}
        </Section>
        <Section className="cuadrao-footer" style={{ padding: "20px 32px", borderTop: `1px solid ${emailBrand.border}` }}>
          <Text className="cuadrao-muted" style={{ margin: "0", color: emailBrand.muted, fontSize: "12px", lineHeight: "20px" }}>Cuadrao LLC</Text>
        </Section>
      </Container>
    </Body>
  </Html>;
}
