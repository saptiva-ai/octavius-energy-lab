/**
 * Default component for (auth) route group
 *
 * This file is required by Next.js for parallel routes.
 * It serves as a fallback when no matching route is found within the (auth) group.
 *
 * Learn more: https://nextjs.org/docs/app/building-your-application/routing/parallel-routes#defaultjs
 */

import { notFound } from "next/navigation";

export default function AuthDefault() {
  // When this component is rendered, it means the user tried to access
  // a route within (auth) that doesn't exist, so we trigger the 404 page
  notFound();
}
