import * as React from "react";
import { render, screen, within, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ConversationList } from "../ConversationList";
import type { ChatSessionOptimistic } from "../../../lib/types";

const pushMock = jest.fn(() => Promise.resolve());

jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: pushMock,
    replace: jest.fn(),
  }),
}));

beforeAll(() => {
  Object.defineProperty(window.HTMLElement.prototype, "scrollIntoView", {
    configurable: true,
    value: jest.fn(),
  });
});

const baseSession: ChatSessionOptimistic = {
  id: "session-1",
  title: "Sesión existente",
  created_at: "2024-01-01T00:00:00.000Z",
  updated_at: "2024-01-01T00:00:00.000Z",
  first_message_at: "2024-01-01T00:05:00.000Z",
  last_message_at: "2024-01-01T00:10:00.000Z",
  message_count: 2,
  model: "turbo",
  preview: "Hola",
  pinned: false,
  state: "active",
};

describe("ConversationList", () => {
  beforeEach(() => {
    pushMock.mockClear();
  });

  it("places pending conversations at the top without duplication", () => {
    const pending: ChatSessionOptimistic = {
      id: "temp-123",
      title: "Nueva conversación",
      created_at: "2024-01-02T00:00:00.000Z",
      updated_at: "2024-01-02T00:00:00.000Z",
      first_message_at: null,
      last_message_at: null,
      message_count: 0,
      model: "turbo",
      preview: "",
      pinned: false,
      state: "creating",
      isOptimistic: true,
      pending: true,
    };

    render(
      <ConversationList
        sessions={[pending, baseSession]}
        onNewChat={async () => pending.id}
        onSelectChat={() => {}}
        activeChatId={pending.id}
        isCreatingConversation
      />,
    );

    const items = screen.getAllByRole("option");
    expect(
      within(items[0]).getByText("Nueva conversación"),
    ).toBeInTheDocument();
  });

  it("disables the create button without showing a spinner", () => {
    render(
      <ConversationList
        sessions={[baseSession]}
        onNewChat={async () => null}
        onSelectChat={() => {}}
        activeChatId={baseSession.id}
        isCreatingConversation
      />,
    );

    const button = screen.getByRole("button", {
      name: "Creando conversación...",
    });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-disabled", "true");
    expect(button.querySelector('[class*="animate-spin"]')).toBeNull();
  });

  it("navigates to optimistic chat id returned by onNewChat", async () => {
    const optimisticId = "temp-456";
    const handleNewChat = jest.fn(async () => optimisticId);

    render(
      <ConversationList
        sessions={[baseSession]}
        onNewChat={handleNewChat}
        onSelectChat={() => {}}
        activeChatId={baseSession.id}
      />,
    );

    const user = userEvent.setup();
    const button = screen.getByRole("button", { name: "Nueva conversación" });
    await act(async () => {
      await user.click(button);
    });

    await waitFor(() => expect(handleNewChat).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(pushMock).toHaveBeenCalledTimes(1));
    expect(pushMock).toHaveBeenCalledWith(`/chat/${optimisticId}`);
  });

  it("ignores repeated clicks while a creation is in-flight", async () => {
    const optimisticId = "temp-789";

    const handleNewChatMock = jest.fn(async () => {
      await new Promise((resolve) => setTimeout(resolve, 25));
      return optimisticId;
    });

    const Wrapper = () => {
      const [isCreating, setIsCreating] = React.useState(false);
      const handleNewChat = React.useCallback(async () => {
        if (isCreating) {
          return null;
        }

        setIsCreating(true);
        const result = await handleNewChatMock();
        setIsCreating(false);
        return result;
      }, [isCreating]);

      return (
        <ConversationList
          sessions={[baseSession]}
          onNewChat={handleNewChat}
          onSelectChat={() => {}}
          activeChatId={baseSession.id}
          isCreatingConversation={isCreating}
        />
      );
    };

    render(<Wrapper />);

    const user = userEvent.setup();
    const firstClickTarget = screen.getByRole("button", {
      name: "Nueva conversación",
    });
    await act(async () => {
      await user.click(firstClickTarget);
    });

    await act(async () => {
      await user.click(firstClickTarget);
    });

    await waitFor(() => expect(pushMock).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(handleNewChatMock).toHaveBeenCalledTimes(1));
  });
});

describe("ConversationList · nombre del producto", () => {
  it("el encabezado del historial dice Energy Ontology Advisor, no OctaviOS Chat", () => {
    // feedback round 1 (2026-10-16, punto 11).
    render(
      <ConversationList
        sessions={[baseSession]}
        onNewChat={async () => null}
        onSelectChat={() => {}}
        activeChatId={baseSession.id}
      />,
    );
    expect(screen.queryByText(/OctaviOS Chat/)).toBeNull();
    expect(screen.getAllByText("Energy Ontology Advisor").length).toBeGreaterThan(0);
  });
});
