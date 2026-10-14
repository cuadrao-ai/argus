import { Button, Section, Text } from "@react-email/components";
import { render, toPlainText } from "@react-email/render";
import { EmailLayout, emailBrand, paragraphStyle } from "./layout";

export function ResetPasswordEmail({ recoveryUrl }: { recoveryUrl: string }) {
  return <EmailLayout preview="Crea una nueva contraseña para tu cuenta.">
    <Text className="cuadrao-copy" style={paragraphStyle}>Hola:</Text>
    <Text className="cuadrao-copy" style={paragraphStyle}>Recibimos una solicitud para cambiar la contraseña de tu cuenta de Cuadrao.</Text>
    <Section style={{ margin: "24px 0" }}>
      <Button className="cuadrao-button" href={recoveryUrl} style={{ boxSizing: "border-box", backgroundColor: emailBrand.pine, color: "#ffffff", padding: "14px 22px", borderRadius: "8px", fontSize: "16px", fontWeight: "bold", textDecoration: "none" }}>Crear nueva contraseña</Button>
    </Section>
    <Text className="cuadrao-copy" style={paragraphStyle}>El enlace vence en 1 hora y solo se puede usar una vez.</Text>
    <Text className="cuadrao-copy" style={paragraphStyle}>Si no pediste este cambio, ignora este correo. Tu contraseña sigue igual.</Text>
    <Text className="cuadrao-copy" style={paragraphStyle}>¿Tienes dudas? Responde a este correo.</Text>
    <Text className="cuadrao-copy" style={{ ...paragraphStyle, marginBottom: "0" }}>Saludos,<br />Cuadrao</Text>
  </EmailLayout>;
}

export async function renderResetPasswordEmail(recoveryUrl: string) {
  const html = await render(<ResetPasswordEmail recoveryUrl={recoveryUrl} />);
  return { subject: "Restablece tu contraseña de Cuadrao", html, text: toPlainText(html) };
}
