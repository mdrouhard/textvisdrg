"""
The view classes below define the API endpoints.

+-----------------------------------------------------------------+-----------------+-------------------------------------------------+
| Endpoint                                                        | Url             | Purpose                                         |
+=================================================================+=================+=================================================+
| :class:`Get Data Table <DataTableView>`                         | /api/table      | Get table of counts based on dimensions/filters |
+-----------------------------------------------------------------+-----------------+-------------------------------------------------+
| :class:`Get Example Messages <ExampleMessagesView>`             | /api/messages   | Get example messages for slice of data          |
+-----------------------------------------------------------------+-----------------+-------------------------------------------------+
| :class:`Get Research Questions <ResearchQuestionsView>`         | /api/questions  | Get RQs related to dimensions/filters           |
+-----------------------------------------------------------------+-----------------+-------------------------------------------------+
| Message Context                                                 | /api/context    | Get context for a message                       |
+-----------------------------------------------------------------+-----------------+-------------------------------------------------+
| Snapshots                                                       | /api/snapshots  | Save a visualization snapshot                   |
+-----------------------------------------------------------------+-----------------+-------------------------------------------------+
"""
import types
from django.db import transaction

from rest_framework import status
from rest_framework.views import APIView, Response
from django.core.urlresolvers import NoReverseMatch
from rest_framework.reverse import reverse
from rest_framework.compat import get_resolver_match, OrderedDict
from django.core.context_processors import csrf
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Count
from django.contrib.auth.models import User

from msgvis.apps.api import serializers
from msgvis.apps.corpus import models as corpus_models
from msgvis.apps.questions import models as questions_models
from msgvis.apps.datatable import models as datatable_models
from msgvis.apps.enhance import models as enhance_models
import msgvis.apps.groups.models as groups_models
import json
import logging

logger = logging.getLogger(__name__)

def add_history(user, type, contents):
    history = groups_models.ActionHistory(type=type, contents=json.dumps(contents), from_server=True)
    if user.id is not None and User.objects.filter(id=1).count() != 0:
        user = User.objects.get(id=user.id)
        history.owner = user
    history.save()

class DataTableView(APIView):
    """
    Get a table of message counts or other statistics based on the current
    dimensions and filters.

    The request should post a JSON object containing a list of one or two
    dimension ids and a list of filters. A ``measure`` may also be specified
    in the request, but the default measure is message count.

    The response will be a JSON object that mimics the request body, but
    with a new ``result`` field added. The result field
    includes a ``table``, which will be a list of objects.

    Each object in the table field represents a cell in a table or a dot
    (for scatterplot-type results). For every dimension in the dimensions
    list (from the request), the result object will include a property keyed
    to the name of the dimension and a value for that dimension. A ``value``
    field provides the requested summary statistic.

    The ``result`` field also includes a ``domains`` object, which
    defines the list of possible values within the selected data
    for each of the dimensions in the request.

    This is the most general output format for results, but later we may
    switch to a more compact format.

    **Request:** ``POST /api/table``

    **Format:** (request without ``result`` key)

    ::

        {
          "dataset": 1,
          "dimensions": ["time"],
          "filters": [
            {
              "dimension": "time",
              "min_time": "2015-02-25T00:23:53Z",
              "max_time": "2015-02-28T00:23:53Z"
            }
          ],
          "result": {
            "table": [
              {
                "value": 35,
                "time": "2015-02-25T00:23:53Z"
              },
              {
                "value": 35,
                "time": "2015-02-26T00:23:53Z"
              },
              {
                "value": 35,
                "time": "2015-02-27T00:23:53Z"
              },
              {
                "value": 35,
                "time": "2015-02-28T00:23:53Z"
              },
              "domains": {
                "time": [
                  "some_time_val",
                  "some_time_val",
                  "some_time_val",
                  "some_time_val"
                ]
              ],
              "domain_labels": {}
        }
    """

    def post(self, request, format=None):
        add_history(self.request.user, 'data-table', request.data)

        input = serializers.DataTableSerializer(data=request.data)
        if input.is_valid():
            data = input.validated_data

            dataset = data['dataset']
            dimensions = data['dimensions']
            filters = data.get('filters', [])
            exclude = data.get('exclude', [])
            search_key = data.get('search_key')
            mode = data.get('mode')
            groups = data.get('groups', [])
            if len(groups) == 0:
                groups = None

            page_size = 100
            page = None
            if data.get('page_size'):
                page_size = data.get('page_size')
                page_size = max(1, int(data.get('page_size')))
            if data.get('page'):
                page = max(1, int(data.get('page')))

            if type(filters) == types.ListType and len(filters) == 0 and \
               type(exclude) == types.ListType and len(exclude) == 0 and len(dimensions) == 1 and dimensions[0].is_categorical():
                result = dataset.get_precalc_distribution(dimension=dimensions[0], search_key=search_key, page=page, page_size=page_size, mode=mode)

            else:

                datatable = datatable_models.DataTable(*dimensions)
                if mode is not None:
                    datatable.set_mode(mode)

                result = datatable.generate(dataset, filters, exclude, page_size, page, search_key, groups)

            # Just add the result key
            response_data = data
            response_data['result'] = result

            output = serializers.DataTableSerializer(response_data)
            return Response(output.data, status=status.HTTP_200_OK)

        return Response(input.errors, status=status.HTTP_400_BAD_REQUEST)


class ExampleMessagesView(APIView):
    """
    Get some example messages matching the current filters and a focus
    within the visualization.

    **Request:** ``POST /api/messages``

    **Format:**: (request should not have ``messages`` key)

    ::

        {
            "dataset": 1,
            "filters": [
                {
                    "dimension": "time",
                    "min_time": "2015-02-25T00:23:53Z",
                    "max_time": "2015-02-28T00:23:53Z"
                }
            ],
            "focus": [
                {
                    "dimension": "time",
                    "value": "2015-02-28T00:23:53Z"
                }
            ],
            "messages": [
                {
                    "id": 52,
                    "dataset": 1,
                    "text": "Some sort of thing or other",
                    "sender": {
                        "id": 2,
                        "dataset": 1
                        "original_id": 2568434,
                        "username": "my_name",
                        "full_name": "My Name"
                    },
                    "time": "2015-02-25T00:23:53Z"
                }
            ]
        }
    """

    def post(self, request, format=None):
        add_history(self.request.user, 'example-messages', request.data)
        input = serializers.ExampleMessageSerializer(data=request.data)
        if input.is_valid():
            data = input.validated_data

            dataset = data['dataset']

            filters = data.get('filters', [])
            excludes = data.get('excludes', [])
            focus = data.get('focus', [])
            groups = data.get('groups')

            if groups is None:
                example_messages = dataset.get_example_messages(filters + focus, excludes)
            else:
                example_messages = dataset.get_example_messages_by_groups(groups, filters + focus, excludes)

            # Just add the messages key to the response
            response_data = data
            response_data["messages"] = example_messages

            output = serializers.ExampleMessageSerializer(response_data, context={'request': request})
            return Response(output.data, status=status.HTTP_200_OK)

        return Response(input.errors, status=status.HTTP_400_BAD_REQUEST)

class KeywordMessagesView(APIView):
    """
    Get some example messages matching the keyword.

    **Request:** ``POST /api/search``

    **Format:**: (request should not have ``messages`` key)

    ::

        {
            "dataset": 1,
            "keywords": "soup ladies,food,NOT job",
            "messages": [
                {
                    "id": 52,
                    "dataset": 1,
                    "text": "Some sort of thing or other",
                    "sender": {
                        "id": 2,
                        "dataset": 1
                        "original_id": 2568434,
                        "username": "my_name",
                        "full_name": "My Name"
                    },
                    "time": "2015-02-25T00:23:53Z"
                }
            ]
        }
    """

    def post(self, request, format=None):
        add_history(self.request.user, 'search', request.data)
        input = serializers.KeywordMessageSerializer(data=request.data)
        if input.is_valid():
            data = input.validated_data

            dataset = data['dataset']

            keywords = data.get('keywords') or ""
            types_list = data.get('types_list') or []
            include_types = []
            if len(types_list) > 0:
                include_types = [corpus_models.MessageType.objects.get(name=x) for x in types_list]

            messages = dataset.get_advanced_search_results(keywords, include_types)

            # Just add the messages key to the response
            response_data = data
            response_data["messages"] = messages

            output = serializers.KeywordMessageSerializer(response_data, context={'request': request})
            return Response(output.data, status=status.HTTP_200_OK)

        return Response(input.errors, status=status.HTTP_400_BAD_REQUEST)

class ActionHistoryView(APIView):
    """
    Add a action history record.

    **Request:** ``POST /api/history``

    **Format:**: (request should not have ``messages`` key)

    ::

        {
           "records": [
               {
                    "type": "click-legend",
                    "contents": "group 10"
                },
                {
                    "type": "group:delete",
                    "contents": "{\\"group\\": 10}"
                }
            ]
        }
    """

    def post(self, request, format=None):
        input = serializers.ActionHistoryListSerializer(data=request.data)
        if input.is_valid():
            data = input.validated_data
            records = []
            owner = None
            if self.request.user is not None:
                user = self.request.user
                if user.id is not None and User.objects.filter(id=1).count() != 0:
                    owner = User.objects.get(id=self.request.user.id)

            for record in data["records"]:
                record_obj = groups_models.ActionHistory(owner=owner, type=record["type"], contents=record["contents"])
                if record.get('created_at'):
                    record_obj.created_at = record.get('created_at')
                records.append(record_obj)

            with transaction.atomic(savepoint=False):
                groups_models.ActionHistory.objects.bulk_create(records)

            return Response(data, status=status.HTTP_200_OK)

        return Response(input.errors, status=status.HTTP_400_BAD_REQUEST)

class GroupView(APIView):
    """
    Get some example messages matching the keyword.

    **Request:** ``POST /api/group``

    **Format:**: (request should not have ``messages`` key)

    ::

        {
            "dataset": 1,
            "keyword": "like",
            "messages": [
                {
                    "id": 52,
                    "dataset": 1,
                    "text": "Some sort of thing or other",
                    "sender": {
                        "id": 2,
                        "dataset": 1
                        "original_id": 2568434,
                        "username": "my_name",
                        "full_name": "My Name"
                    },
                    "time": "2015-02-25T00:23:53Z"
                }
            ]
        }
    """


    def post(self, request, format=None):
        add_history(self.request.user, 'group:create', request.data)
        input = serializers.GroupSerializer(data=request.data)
        if input.is_valid():
            data = input.validated_data
            group = input.save()
            user = self.request.user
            if user.id is not None and User.objects.filter(id=1).count() != 0:
                owner = User.objects.get(id=self.request.user.id)
                group.owner = owner
                if not data.get('is_search_record'):
                    group.order = groups_models.Group.objects.filter(owner=owner, is_search_record=False).count() + 1
                else:
                    group.is_search_record = True
                    group.order = 0
                group.save()

            # Just add the messages key to the response

            output = serializers.GroupSerializer(group, context={'request': request, 'show_message': False})
            return Response(output.data, status=status.HTTP_200_OK)

        return Response(input.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, format=None):
        if request.query_params.get('dataset'):
            add_history(self.request.user, 'group:get-list', request.query_params)
            dataset_id = int(request.query_params.get('dataset'))
            groups = groups_models.Group.objects.filter(dataset_id=dataset_id, deleted=False)
            user = self.request.user
            if user.id is not None and User.objects.filter(id=1).count() != 0:
                owner = User.objects.get(id=self.request.user.id)
                groups = groups.filter(owner=owner)
            groups = groups.order_by('order', 'created_at').all()
            output = serializers.GroupSerializer(groups, many=True)
            return Response(output.data, status=status.HTTP_200_OK)
        elif request.query_params.get('group_id'):
            add_history(self.request.user, 'group:get-single-group', request.data)
            group = groups_models.Group.objects.get(id=int(request.query_params.get('group_id')))
            output = serializers.GroupSerializer(group, context={'request': request, 'show_message': True})
            return Response(output.data, status=status.HTTP_200_OK)
        else:
            add_history(self.request.user, 'group:get-all-groups', request.data)
            groups = groups_models.Group.objects.all()
            output = serializers.GroupSerializer(groups, many=True)
            return Response(output.data, status=status.HTTP_200_OK)

    def put(self, request, format=None):
        add_history(self.request.user, 'group:update', request.data)
        input = serializers.GroupSerializer(data=request.data)
        if input.is_valid():
            data = input.validated_data
            group = groups_models.Group.objects.get(id=request.data["id"])
            if data.get('name') is not None:
                group.name = data["name"]
                group.save()
            if data.get('keywords') is not None:
                group.keywords = data.get('keywords')
                group.save()

            if data.get('types_list') is not None:
                type_list = data.get('types_list')
                include_types = map(lambda x: corpus_models.MessageType.objects.get(name=x), type_list)
                group.include_types.clear()
                group.include_types = include_types


            output = serializers.GroupSerializer(group, context={'request': request, 'show_message': False})
            return Response(output.data, status=status.HTTP_200_OK)

        return Response(input.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, format=None):
        add_history(self.request.user, 'group:delete', request.query_params)
        if request.query_params.get('id'):
            group = groups_models.Group.objects.get(id=request.query_params.get('id'))
            if group:
                group.deleted = True
                group.save()
            return Response(status=status.HTTP_204_NO_CONTENT)


class KeywordView(APIView):
    """
    Get top 10 keyword results.

    **Request:** ``GET /api/keyword?dataset=1&q= [...]``

    ::

        {
            "dataset": 1,
            "q": "mudslide oso",
            "keywords": ["mudslide oso", "mudslide oso soup", "mudslide oso ladies"]
        }
    """


    def get(self, request, format=None):
        add_history(self.request.user, 'auto-complete:get-list', request.query_params)
        if request.query_params.get('dataset'):
            dataset_id = request.query_params.get('dataset')
            response_data = {
                "dataset": dataset_id
            }

            if request.query_params.get('q') is None:
                keywords = enhance_models.TweetWord.objects.filter(dataset_id=dataset_id).values('text').distinct()[:20]
                response_data["keywords"] = keywords
                output = serializers.KeywordListSerializer(response_data)
            else:
                q = request.query_params.get('q')
                response_data["q"] = q

                strings = q.split(' ')
                prefix = " ".join(strings[:-1]) + " "
                keyword = strings[-1]
                keywords = enhance_models.PrecalcCategoricalDistribution.objects.filter(dataset_id=dataset_id,
                                                                                        dimension_key="words",
                                                                                        level__istartswith=keyword).order_by('-count')

                response_data["keywords"] = map(lambda x: prefix + x.level, keywords[:20])
                output = serializers.KeywordListSerializer(response_data)

                for idx, keyword in enumerate(output.data['keywords']):
                    output.data['keywords'][idx] = {"text": output.data['keywords'][idx]}

            #output = serializers.GroupListItemSerializer(group, context={'request': request})
            return Response(output.data, status=status.HTTP_200_OK)

        return Response(status=status.HTTP_400_BAD_REQUEST)

class ResearchQuestionsView(APIView):
    """
    Get a list of research questions related to a selection of dimensions and filters.

    **Request:** ``POST /api/questions``

    **Format:** (request without ``questions`` key)

    ::

        {
            "dimensions": ["time", "hashtags"],
            "questions": [
                {
                  "id": 5,
                  "text": "What is your name?",
                  "source": {
                    "id": 13,
                    "authors": "Thingummy & Bob",
                    "link": "http://ijn.com/3453295",
                    "title": "Names and such",
                    "year": "2001",
                    "venue": "International Journal of Names"
                  },
                  "dimensions": ["time", "author_name"]
                }
            ]
        }
    """

    def post(self, request, format=None):
        input = serializers.SampleQuestionSerializer(data=request.data)
        if input.is_valid():
            data = input.validated_data
            dimension_list = data["dimensions"]
            questions = questions_models.Question.get_sample_questions(*dimension_list)

            response_data = {
                "dimensions": dimension_list,
                "questions": questions
            }

            output = serializers.SampleQuestionSerializer(response_data)
            return Response(output.data, status=status.HTTP_200_OK)

        return Response(input.errors, status=status.HTTP_400_BAD_REQUEST)


class DatasetView(APIView):
    """
    Get details of a dataset

    **Request:** ``GET /api/dataset/1``
    """


    def get(self, request, format=None):
        if request.query_params.get('id'):
            dataset_id = int(request.query_params.get('id'))
            try:
                dataset = corpus_models.Dataset.objects.get(id=dataset_id)
                output = serializers.DatasetSerializer(dataset)
                return Response(output.data, status=status.HTTP_200_OK)
            except:
                return Response("Dataset not exist", status=status.HTTP_400_BAD_REQUEST)

        return Response("Please specify dataset id", status=status.HTTP_400_BAD_REQUEST)


class APIRoot(APIView):
    """
    The Text Visualization DRG Root API View.
    """
    root_urls = {}

    def get(self, request, *args, **kwargs):
        ret = OrderedDict()
        namespace = get_resolver_match(request).namespace
        for key, urlconf in self.root_urls.iteritems():
            url_name = urlconf.name
            if namespace:
                url_name = namespace + ':' + url_name
            try:
                ret[key] = reverse(
                    url_name,
                    request=request,
                    format=kwargs.get('format', None)
                )
                print ret[key]
            except NoReverseMatch:
                # Don't bail out if eg. no list routes exist, only detail routes.
                continue

        return Response(ret)
