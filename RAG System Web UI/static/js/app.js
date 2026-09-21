// === Инициализация приложения ===
document.addEventListener('DOMContentLoaded', () => {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.forEach(tooltipTriggerEl => {
        new bootstrap.Tooltip(tooltipTriggerEl);
    });

    Chat.init();
    History.loadConversations(true);
    Chat.restoreLastConversation();

    MemoWizard.restoreSession();

    const newChatBtn = document.getElementById('newChatBtn');
    if (newChatBtn) newChatBtn.addEventListener('click', () => Chat.startNewChat());

    const clearHistoryBtn = document.getElementById('clearHistoryBtn');
    if (clearHistoryBtn) clearHistoryBtn.addEventListener('click', () => History.clearAll());

    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.addEventListener('click', () => History.switchTab(btn.dataset.tab));
    });

    const copyButton = document.getElementById('copyButton');
    if (copyButton) {
        copyButton.addEventListener('click', () => {
            copyText(document.getElementById('filePath').value, copyButton);
        });
    }

    // Бесконечная прокрутка истории
    const historyContent = document.getElementById('historyContent');
    historyContent.addEventListener('scroll', () => {
        if (historyContent.scrollTop + historyContent.clientHeight >= historyContent.scrollHeight - 50) {
            if (History.activeTab === 'conversations') {
                History.loadConversations();
            } else {
                History.loadFavorites();
            }
        }
    });

    Sync.start();
});