# -*- coding: utf-8 -*-
from Products.CMFCore.utils import getToolByName
from plone.app.textfield.value import RichTextValue
from plone.app.robotframework.remote import RemoteLibrary
from plone.namedfile.file import NamedBlobFile
from plone.namedfile.file import NamedBlobImage
from plone.uuid.interfaces import IUUID
from zope.component.hooks import getSite
from zope.component import getUtility, ComponentLookupError

import os
import pkg_resources

try:
    pkg_resources.get_distribution('plone.dexterity')
except pkg_resources.DistributionNotFound:
    HAS_DEXTERITY = False
else:
    HAS_DEXTERITY = True


class Content(RemoteLibrary):

    def create_content(self, *args, **kwargs):
        """Create content and return its UID"""
        # XXX: Because kwargs are only supported with robotframework >= 2.8.3,
        # we must parse them here to support robotframework < 2.8.3.
        for arg in [x for x in args if '=' in x]:
            name, value = arg.split('=', 1)
            kwargs[name] = value

        assert 'id' in kwargs, u"Keyword arguments must include 'id'."
        assert 'type' in kwargs, u"Keyword arguments must include 'type'."
        portal = getSite()
        if 'container' in kwargs:
            pc = getToolByName(portal, 'portal_catalog')
            uid_or_path = kwargs.pop('container')
            uid_results =\
                pc.unrestrictedSearchResults(UID=uid_or_path)
            path_results = \
                pc.unrestrictedSearchResults(
                    path={'query': uid_or_path.rstrip('/'), 'depth': 0})
            container =\
                (uid_results or path_results)[0]._unrestrictedGetObject()
        else:
            container = portal

        # Pre-fill Image-types with random content
        if kwargs.get('type') == 'Image' and not 'image' in kwargs:
            import random
            import StringIO
            from PIL import (
                Image,
                ImageDraw
            )
            img = Image.new('RGB', (random.randint(320, 640),
                                    random.randint(320, 640)))
            draw = ImageDraw.Draw(img)
            draw.rectangle(((0, 0), img.size), fill=(random.randint(0, 255),
                                                     random.randint(0, 255),
                                                     random.randint(0, 255)))
            del draw

            kwargs['image'] = StringIO.StringIO()
            img.save(kwargs['image'], 'PNG')
            kwargs['image'].seek(0)

        id_ = kwargs.pop('id')
        type_ = kwargs.pop('type')

        content = None
        if HAS_DEXTERITY:
            # The title attribute for Dexterity types needs to be unicode
            if isinstance(kwargs['title'], str):
                kwargs['title'] = kwargs['title'].decode('utf-8')
            from plone.dexterity.interfaces import IDexterityFTI
            from plone.dexterity.utils import createContentInContainer
            try:
                getUtility(IDexterityFTI, name=type_)
                content = createContentInContainer(container, type_, **kwargs)
                if content.id != id_:
                    container.manage_renameObject(content.id, id_)
            except ComponentLookupError:
                pass

        if content is None:
            # It must be Archetypes based content:
            content = container[container.invokeFactory(type_, id_, **kwargs)]
            content.processForm()

        return IUUID(content)

    def set_field_value(self, uid, field, value, field_type):
        """Set field value with a specific type"""
        pc = getToolByName(self, 'portal_catalog')
        results = pc.unrestrictedSearchResults(UID=uid)
        obj = results[0]._unrestrictedGetObject()
        if field_type == 'float':
            value = float(value)
        if field_type == 'int':
            value = int(value)
        if field_type == 'list':
            value = eval(value)
        if field_type == 'reference':
            results_referenced = pc.unrestrictedSearchResults(UID=value)
            referenced_obj = results_referenced[0]._unrestrictedGetObject()
            from zope.app.intid.interfaces import IIntIds
            from zope.component import getUtility
            intids = getUtility(IIntIds)
            referenced_obj_intid = intids.getId(referenced_obj)
            from z3c.relationfield import RelationValue
            value = RelationValue(referenced_obj_intid)
        if field_type == 'text/html':
            value = RichTextValue(
                value,
                'text/html',
                'text/html'
            )
            obj.text = value
        if field_type == 'file':
            pdf_file = os.path.join(
                os.path.dirname(__file__), 'content', u'file.pdf')
            value = NamedBlobFile(
                data=open(pdf_file, 'r').read(),
                contentType='application/pdf',
                filename=u'file.pdf'
            )
        if field_type == 'image':
            image_file = os.path.join(
                os.path.dirname(__file__), u'image.jpg')
            value = NamedBlobImage(
                data=open(image_file, 'r').read(),
                contentType='image/jpg',
                filename=u'image.jpg'
            )

        setattr(obj, field, value)
        obj.reindexObject()

    def uid_to_url(self, uid):
        """Return absolute path for an UID"""
        pc = getToolByName(self, 'portal_catalog')
        results = pc.unrestrictedSearchResults(UID=str(uid))
        if not results:
            return None
        else:
            return results[0].getURL()

    def path_to_uid(self, path):
        """Return UID for an absolute path"""
        pc = getToolByName(self, 'portal_catalog')
        results = pc.unrestrictedSearchResults(
            path={'query': path.rstrip('/'), 'depth': 0})
        if not results:
            return None
        else:
            return results[0].UID

    def fire_transition(self, content, action):
        """Fire workflow action for content"""
        # It should be ok to use unrestricted-methods, because workflow
        # transition guard should proctect unprivileged transition:
        pc = getToolByName(self, 'portal_catalog')
        results = pc.unrestrictedSearchResults(UID=content)
        obj = results[0]._unrestrictedGetObject()
        wftool = getToolByName(obj, 'portal_workflow')
        wftool.doActionFor(obj, action)

    do_action_for = fire_transition