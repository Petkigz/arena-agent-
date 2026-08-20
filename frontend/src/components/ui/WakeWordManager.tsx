import { useEffect } from 'react';
import { useWakeWordStore } from '../../stores/wakeWordStore';
import { Button } from './Button';
import { Check, Trash2, Zap, Star } from 'lucide-react';

export function WakeWordManager() {
  const { models, activeModel, fetchModels, fetchActiveModel, activateModel, deleteModel } =
    useWakeWordStore();

  useEffect(() => {
    fetchModels();
    fetchActiveModel();
  }, [fetchModels, fetchActiveModel]);

  if (models.length === 0) {
    return (
      <div className="text-center py-8">
        <Zap className="w-12 h-12 text-text-muted mx-auto mb-4" />
        <h3 className="text-lg font-semibold text-text-primary mb-2">No Wake Word Models</h3>
        <p className="text-text-secondary">
          Train a custom wake word model to get started
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold text-text-primary">Your Wake Word Models</h3>

      <div className="space-y-3">
        {models.map((model) => (
          <div
            key={model.id}
            className={`p-4 rounded-lg border-2 transition-colors ${
              model.isActive
                ? 'border-accent-primary bg-accent-primary/10'
                : 'border-border bg-background-surface'
            }`}
          >
            <div className="flex items-start justify-between mb-3">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <h4 className="font-semibold text-text-primary">{model.name}</h4>
                  {model.isActive && (
                    <span className="px-2 py-0.5 bg-accent-primary text-white text-xs rounded-full">
                      Active
                    </span>
                  )}
                </div>
                <p className="text-sm text-text-secondary mb-2">
                  Wake word: <span className="font-medium">"{model.wakeWord}"</span>
                </p>
                <div className="flex items-center gap-4 text-xs text-text-muted">
                  <span>{model.sampleCount} samples</span>
                  {model.accuracy && (
                    <span>Accuracy: {Math.round(model.accuracy * 100)}%</span>
                  )}
                  <span>{new Date(model.createdAt).toLocaleDateString()}</span>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {!model.isActive ? (
                <Button
                  onClick={() => activateModel(model.id)}
                  variant="primary"
                  size="sm"
                  className="flex-1"
                >
                  <Star className="w-4 h-4 mr-2" />
                  Activate
                </Button>
              ) : (
                <div className="flex items-center gap-2 text-sm text-accent-primary flex-1">
                  <Check className="w-4 h-4" />
                  <span>Currently active</span>
                </div>
              )}

              <Button
                onClick={() => deleteModel(model.id)}
                variant="secondary"
                size="sm"
              >
                <Trash2 className="w-4 h-4" />
              </Button>
            </div>
          </div>
        ))}
      </div>

      {activeModel && (
        <div className="p-4 bg-accent-primary/10 border border-accent-primary/30 rounded-lg">
          <div className="flex items-start gap-3">
            <Star className="w-5 h-5 text-accent-primary flex-shrink-0 mt-0.5" />
            <div>
              <h4 className="font-semibold text-text-primary mb-1">Active Wake Word</h4>
              <p className="text-sm text-text-secondary">
                Say <span className="font-medium">"{activeModel.wakeWord}"</span> to activate Arena
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
