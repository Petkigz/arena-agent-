import { useState } from 'react';
import { useConversationStore } from '../../stores';
import { Button } from '../ui/Button';
import { Search, Filter, X, Calendar, Folder, CheckCircle, XCircle } from 'lucide-react';

export function ConversationFilters() {
  const { conversations } = useConversationStore();
  const [showFilters, setShowFilters] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [dateRange, setDateRange] = useState<{ start: string; end: string }>({
    start: '',
    end: '',
  });
  const [selectedProject, setSelectedProject] = useState<string>('');
  const [selectedOutcome, setSelectedOutcome] = useState<'all' | 'success' | 'failed'>('all');

  // Get unique projects from conversations
  const projects = Array.from(
    new Set(conversations.map((c) => c.projectId).filter(Boolean))
  );

  // Filter conversations based on current filters
  const filteredConversations = conversations.filter((conversation) => {
    // Search query filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      const matchesTitle = conversation.title.toLowerCase().includes(query);
      const matchesMessages = conversation.messages.some((m) =>
        m.content.toLowerCase().includes(query)
      );
      if (!matchesTitle && !matchesMessages) return false;
    }

    // Date range filter
    if (dateRange.start || dateRange.end) {
      const conversationDate = new Date(conversation.updatedAt);
      
      if (dateRange.start) {
        const startDate = new Date(dateRange.start);
        if (conversationDate < startDate) return false;
      }
      
      if (dateRange.end) {
        const endDate = new Date(dateRange.end);
        endDate.setHours(23, 59, 59, 999); // End of day
        if (conversationDate > endDate) return false;
      }
    }

    // Project filter
    if (selectedProject && conversation.projectId !== selectedProject) {
      return false;
    }

    // Outcome filter (based on last message status or action steps)
    if (selectedOutcome !== 'all') {
      const hasFailedActions = conversation.messages.some((m) =>
        m.actionSteps?.some((step) => step.status === 'error')
      );
      const hasSuccessActions = conversation.messages.some((m) =>
        m.actionSteps?.some((step) => step.status === 'complete')
      );

      if (selectedOutcome === 'success' && !hasSuccessActions) return false;
      if (selectedOutcome === 'failed' && !hasFailedActions) return false;
    }

    return true;
  });

  const activeFiltersCount = [
    searchQuery,
    dateRange.start,
    dateRange.end,
    selectedProject,
    selectedOutcome !== 'all',
  ].filter(Boolean).length;

  const clearFilters = () => {
    setSearchQuery('');
    setDateRange({ start: '', end: '' });
    setSelectedProject('');
    setSelectedOutcome('all');
  };

  return (
    <div className="space-y-3">
      {/* Search bar */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search conversations..."
          className="w-full pl-10 pr-10 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary"
        />
        {searchQuery && (
          <button
            onClick={() => setSearchQuery('')}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Filter toggle */}
      <div className="flex items-center gap-2">
        <Button
          onClick={() => setShowFilters(!showFilters)}
          variant="secondary"
          size="sm"
          className="flex items-center gap-2"
        >
          <Filter className="w-4 h-4" />
          <span>Filters</span>
          {activeFiltersCount > 0 && (
            <span className="px-2 py-0.5 bg-accent-primary text-white text-xs rounded-full">
              {activeFiltersCount}
            </span>
          )}
        </Button>

        {activeFiltersCount > 0 && (
          <button
            onClick={clearFilters}
            className="text-sm text-text-muted hover:text-text-primary transition-colors"
          >
            Clear all
          </button>
        )}

        <span className="text-sm text-text-muted ml-auto">
          {filteredConversations.length} conversation{filteredConversations.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Filter panel */}
      {showFilters && (
        <div className="p-4 bg-background-secondary rounded-lg space-y-4">
          {/* Date range */}
          <div>
            <label className="flex items-center gap-2 text-sm font-medium text-text-primary mb-2">
              <Calendar className="w-4 h-4" />
              Date Range
            </label>
            <div className="flex items-center gap-2">
              <input
                type="date"
                value={dateRange.start}
                onChange={(e) => setDateRange({ ...dateRange, start: e.target.value })}
                className="flex-1 px-3 py-2 bg-background-surface border border-border rounded focus:outline-none focus:ring-2 focus:ring-accent-primary"
                placeholder="Start date"
              />
              <span className="text-text-muted">to</span>
              <input
                type="date"
                value={dateRange.end}
                onChange={(e) => setDateRange({ ...dateRange, end: e.target.value })}
                className="flex-1 px-3 py-2 bg-background-surface border border-border rounded focus:outline-none focus:ring-2 focus:ring-accent-primary"
                placeholder="End date"
              />
            </div>
          </div>

          {/* Project filter */}
          {projects.length > 0 && (
            <div>
              <label className="flex items-center gap-2 text-sm font-medium text-text-primary mb-2">
                <Folder className="w-4 h-4" />
                Project
              </label>
              <select
                value={selectedProject}
                onChange={(e) => setSelectedProject(e.target.value)}
                className="w-full px-3 py-2 bg-background-surface border border-border rounded focus:outline-none focus:ring-2 focus:ring-accent-primary"
              >
                <option value="">All projects</option>
                {projects.map((project) => (
                  <option key={project} value={project}>
                    {project}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Outcome filter */}
          <div>
            <label className="flex items-center gap-2 text-sm font-medium text-text-primary mb-2">
              <CheckCircle className="w-4 h-4" />
              Outcome
            </label>
            <div className="flex gap-2">
              <button
                onClick={() => setSelectedOutcome('all')}
                className={`flex-1 px-3 py-2 rounded text-sm font-medium transition-colors ${
                  selectedOutcome === 'all'
                    ? 'bg-accent-primary text-white'
                    : 'bg-background-surface text-text-secondary hover:bg-background-surface/80'
                }`}
              >
                All
              </button>
              <button
                onClick={() => setSelectedOutcome('success')}
                className={`flex-1 px-3 py-2 rounded text-sm font-medium transition-colors flex items-center justify-center gap-1 ${
                  selectedOutcome === 'success'
                    ? 'bg-accent-success text-white'
                    : 'bg-background-surface text-text-secondary hover:bg-background-surface/80'
                }`}
              >
                <CheckCircle className="w-4 h-4" />
                Success
              </button>
              <button
                onClick={() => setSelectedOutcome('failed')}
                className={`flex-1 px-3 py-2 rounded text-sm font-medium transition-colors flex items-center justify-center gap-1 ${
                  selectedOutcome === 'failed'
                    ? 'bg-accent-error text-white'
                    : 'bg-background-surface text-text-secondary hover:bg-background-surface/80'
                }`}
              >
                <XCircle className="w-4 h-4" />
                Failed
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
