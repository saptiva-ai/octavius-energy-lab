import { getFriendlyName, type UserLike } from "@/utils/user";

type Props = {
  user?: UserLike;
};

export default function WelcomeBanner({ user }: Props) {
  const name = getFriendlyName(user);
  return (
    <div className="w-full flex justify-center px-4 mt-10">
      <div
        className="
        max-w-2xl w-full text-center
        text-zinc-200
      "
      >
        <div
          className="inline-flex items-center gap-2 px-3 py-1
                        rounded-full border border-zinc-700/60
                        text-xs tracking-wide uppercase text-zinc-300/90"
        >
          Saptiva OctaviOS Chat
        </div>
        <h1 className="mt-4 text-3xl md:text-4xl font-semibold text-zinc-100">
          Hola, {name}. Bienvenido a{" "}
          <span className="text-zinc-100">Saptiva</span>
        </h1>
        <p className="mt-2 text-zinc-400">
          Este es tu espacio de conversación. Escribe tu mensaje para comenzar.
        </p>
      </div>
    </div>
  );
}
