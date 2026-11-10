export type UserLike = {
  displayName?: string | null;
  name?: string | null;
  username?: string | null;
  email?: string | null;
};

export function getFriendlyName(user?: UserLike): string {
  if (!user) return "Usuario";
  const n = user.displayName?.trim() || user.name?.trim() || user.username?.trim();
  if (n && n.length > 0) return n;
  const mail = user.email?.trim();
  if (mail && mail.includes("@")) return mail.split("@")[0];
  return "Usuario";
}