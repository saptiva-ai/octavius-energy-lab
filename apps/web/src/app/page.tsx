import { redirect } from "next/navigation";

/**
 * Root page - redirects to login.
 *
 * The landing page was removed to reduce friction in the user flow.
 * Users go directly to login, and if they need an account they contact
 * an administrator (no self-registration).
 */
export default function HomePage() {
  redirect("/login");
}
