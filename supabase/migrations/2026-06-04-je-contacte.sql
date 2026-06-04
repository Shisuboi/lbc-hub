-- Migration : signal de contact dans item_comments

-- 1. Nouvelles colonnes sur item_comments
ALTER TABLE item_comments
  ADD COLUMN IF NOT EXISTS type TEXT NOT NULL DEFAULT 'comment',
  ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ;

-- 2. Index unique partiel : un seul signal actif par opportunité
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_contact
  ON item_comments(opportunity_id)
  WHERE type = 'contact' AND cancelled_at IS NULL;

-- 3. RPC : créer un signal de contact (depuis le hub, utilisateur authentifié)
CREATE OR REPLACE FUNCTION create_contact_signal(p_opportunity_id UUID)
RETURNS SETOF item_comments
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE v_username TEXT;
BEGIN
  SELECT username INTO v_username FROM profiles WHERE id = auth.uid();
  IF v_username IS NULL THEN
    RAISE EXCEPTION 'Profil introuvable.';
  END IF;
  RETURN QUERY
    INSERT INTO item_comments(opportunity_id, user_id, body, type)
    VALUES (
      p_opportunity_id,
      auth.uid(),
      '🤝 ' || v_username || ' s''en occupe',
      'contact'
    )
    RETURNING *;
END;
$$;

-- 4. RPC : annuler un signal de contact (auteur ou admin)
CREATE OR REPLACE FUNCTION cancel_contact_signal(p_comment_id UUID)
RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM item_comments ic
    WHERE ic.id = p_comment_id
    AND (
      ic.user_id = auth.uid()
      OR EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin')
    )
  ) THEN
    RAISE EXCEPTION 'Accès refusé.';
  END IF;
  UPDATE item_comments SET cancelled_at = now() WHERE id = p_comment_id;
END;
$$;
