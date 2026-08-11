import { AuthCard } from "@/components/AuthCard";
import { RegisterForm } from "./RegisterForm";

export default function RegisterPage() {
  return (
    <AuthCard title="Create an account" subtitle="Join the marketplace">
      <RegisterForm />
    </AuthCard>
  );
}
